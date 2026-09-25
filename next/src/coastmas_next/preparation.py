"""Native-grid indicator production and explicit reference-grid adaptation.

These operators consume fixed task inputs and produce actual files. They never
require evaluation weights; an output is not an approved ecological score.
"""

import hashlib
from contextlib import ExitStack
from typing import Literal

import numpy as np
import rasterio
from coastmas.core.contracts import UNITS
from coastmas.core.errors import ConstraintError
from coastmas.domain.assessment import normalize
from pydantic import Field, StrictBool, ValidationError, model_validator
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT
from rasterio.windows import Window

from .contracts import Contract
from .geospatial_view import band_check, data_mask, georeference
from .store import Problem


class AlignOptions(Contract):
    reference_asset_id: str
    quantity_kind: Literal["category", "continuous"]
    resampling: Literal["nearest", "bilinear"]


class NdviOptions(Contract):
    red_band: int = Field(ge=1)
    nir_band: int = Field(ge=1)
    qa_policy: Literal["source_mask", "accepted_codes"]
    qa_band: int | None = Field(default=None, ge=1)
    accepted_codes: list[int] = Field(default_factory=list, max_length=256)


class ScoreOptions(Contract):
    concept: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    lower: float = Field(allow_inf_nan=False)
    upper: float = Field(allow_inf_nan=False)
    positive: StrictBool
    missing_policy: Literal["preserve_mask"]
    basis: str = Field(min_length=1)

    @model_validator(mode="after")
    def interval(self):
        if self.upper <= self.lower:
            raise ValueError("评分参考上限必须大于下限")
        try:
            UNITS.Unit(self.unit)
        except Exception as exc:
            raise ValueError("评分单位无法识别") from exc
        return self


def options(operator, parameters):
    try:
        value = {"align_grid": AlignOptions, "ndvi": NdviOptions, "score": ScoreOptions}[
            operator
        ].model_validate(parameters)
    except ValidationError as exc:
        raise Problem(
            422,
            "PROCESSING_PARAMETERS",
            "请补齐本步必要参数",
            {"errors": exc.errors(include_url=False, include_context=False)},
        ) from exc
    if (
        isinstance(value, AlignOptions)
        and value.quantity_kind == "category"
        and value.resampling != "nearest"
    ):
        raise Problem(422, "CATEGORY_RESAMPLING", "分类资料不能使用双线性插值，请选择最近邻。")
    if isinstance(value, NdviOptions):
        if value.red_band == value.nir_band:
            raise Problem(422, "SPECTRAL_BANDS", "红光和近红外必须对应不同波段。")
        if value.qa_policy == "accepted_codes" and (
            value.qa_band is None or not value.accepted_codes
        ):
            raise Problem(422, "QA_RULE", "请选择质量波段与可接受的质量码。")
    return value


def grid(ds):
    return {
        "width": ds.width,
        "height": ds.height,
        "crs": ds.crs.to_string(),
        "transform": list(ds.transform)[:6],
    }


def preflight(settings, draft, sources):
    operator = draft["options"]["operator"]
    parameters = options(operator, draft["options"].get("parameters", {}))
    if not sources or any(a["facts"]["profile"] not in {"geotiff", "cog"} for a in sources):
        raise Problem(422, "RASTER_REQUIRED", "本步需要可读取的栅格资料。")
    with ExitStack() as stack:
        opened = {
            a["id"]: stack.enter_context(rasterio.open(settings.storage_root / a["object_key"]))
            for a in sources
        }
        for ds in opened.values():
            located, _, issue = georeference(ds)
            if located != "located":
                raise Problem(422, "SOURCE_LOCATION", issue)
        source = opened[sources[0]["id"]]
        band = draft["options"].get("band", 1)
        band_check(source, band)
        target = source
        if isinstance(parameters, AlignOptions):
            target = opened.get(parameters.reference_asset_id)
            if target is None:
                raise Problem(422, "REFERENCE_REQUIRED", "参考栅格必须已加入本研究。")
        elif isinstance(parameters, NdviOptions):
            band_check(source, parameters.red_band)
            band_check(source, parameters.nir_band)
            if parameters.qa_policy == "accepted_codes":
                band_check(source, parameters.qa_band)
        if isinstance(parameters, ScoreOptions):
            try:
                unit = source.units[band - 1] or parameters.unit
                UNITS.Quantity(1, unit).to(parameters.unit)
            except Exception as exc:
                raise Problem(422, "SCORE_UNIT", "原值单位与评分规则不兼容") from exc
        return {
            "id": f"builtin:{operator}:1",
            "version": 1,
            "operator": operator,
            "parameters": parameters.model_dump(),
            "output_grid": grid(target),
            "adaptation": "same_grid" if grid(target) == grid(source) else "reference_grid",
            "source_grid": grid(source),
            "expected_outputs": [
                {
                    "name": {"align_grid": "aligned.tif", "ndvi": "ndvi.tif", "score": "score.tif"}[
                        operator
                    ],
                    "role": {
                        "align_grid": "prepared_input",
                        "ndvi": "raw_indicator",
                        "score": "indicator",
                    }[operator],
                    "view_kind": "raster",
                }
            ],
        }


def compute(settings, manifest, cancelled, artifact_dir):
    draft = manifest["draft"]
    method = preflight(settings, draft, manifest["assets"])
    if method != manifest["method"]:
        raise Problem(409, "PROCESSING_CHANGED", "本步输入或参数已变化。")
    params = options(method["operator"], draft["options"].get("parameters", {}))
    artifact_dir.mkdir(parents=True, exist_ok=True)
    item = method["expected_outputs"][0]
    path = artifact_dir / item["name"]
    spec = method["output_grid"]
    valid_count = 0
    with ExitStack() as stack:
        stack.enter_context(rasterio.Env(GDAL_CACHEMAX=64 * 1024**2))
        source = stack.enter_context(
            rasterio.open(settings.storage_root / manifest["assets"][0]["object_key"])
        )
        reader = source
        if isinstance(params, AlignOptions) and method["adaptation"] != "same_grid":
            reader = stack.enter_context(
                WarpedVRT(
                    source,
                    crs=spec["crs"],
                    transform=rasterio.Affine(*spec["transform"]),
                    width=spec["width"],
                    height=spec["height"],
                    resampling=Resampling[params.resampling],
                    dtype="float64",
                    nodata=np.nan,
                    warp_mem_limit=64,
                )
            )
        target = stack.enter_context(
            rasterio.open(
                path,
                "w",
                driver="GTiff",
                width=spec["width"],
                height=spec["height"],
                count=1,
                dtype="float64",
                nodata=np.nan,
                transform=rasterio.Affine(*spec["transform"]),
                crs=spec["crs"],
                tiled=True,
                blockxsize=256,
                blockysize=256,
                compress="deflate",
            )
        )
        band = draft["options"].get("band", 1)
        unit = source.units[band - 1] if isinstance(params, AlignOptions) else "1"
        if unit:
            target.set_band_unit(1, unit)
        for row in range(0, spec["height"], 512):
            for col in range(0, spec["width"], 512):
                if cancelled.is_set():
                    raise Problem(409, "CANCELLED", "本步处理已取消。")
                window = Window(
                    col, row, min(512, spec["width"] - col), min(512, spec["height"] - row)
                )
                if isinstance(params, AlignOptions):
                    values, valid = data_mask(reader, band, window=window)
                elif isinstance(params, ScoreOptions):
                    values, valid = data_mask(source, band, window=window)
                    physical = (
                        UNITS.Quantity(values[valid], source.units[band - 1] or params.unit)
                        .to(params.unit)
                        .magnitude
                    )
                    try:
                        scored = normalize(
                            physical[:, None], [params.lower], [params.upper], [params.positive]
                        )[:, 0]
                    except ConstraintError as exc:
                        raise Problem(
                            422,
                            "SCORE_RANGE",
                            "原值超出固定评分参考范围，请修订规则后重试；不能静默截断。",
                        ) from exc
                    values = np.full(values.shape, np.nan)
                    values[valid] = scored
                else:
                    red, rv = data_mask(source, params.red_band, window=window)
                    nir, nv = data_mask(source, params.nir_band, window=window)
                    denominator = nir + red
                    valid = rv & nv & np.isfinite(denominator) & (denominator != 0)
                    if params.qa_policy == "accepted_codes":
                        qa = source.read(params.qa_band, window=window, masked=True)
                        valid &= ~np.ma.getmaskarray(qa) & np.isin(qa.data, params.accepted_codes)
                    values = np.full(red.shape, np.nan, dtype="float64")
                    np.divide(nir - red, denominator, out=values, where=valid)
                    valid &= np.isfinite(values)
                valid_count += int(valid.sum())
                target.write(np.where(valid, values, np.nan), 1, window=window)
        target.update_tags(
            operator=method["operator"],
            scope="full_grid",
            source_sha256=manifest["assets"][0]["sha256"],
        )
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {
        "scope": "full_grid",
        "operator": method["operator"],
        "method": method,
        "business_validated": False,
        "statistics": {
            "scope": "full_grid",
            "total_pixels": spec["width"] * spec["height"],
            "valid_pixels": valid_count,
        },
        "files": [
            {
                **item,
                "key": str(path.relative_to(settings.storage_root)),
                "size": path.stat().st_size,
                "sha256": digest,
                "title": {
                    "align_grid": "统一空间后的资料",
                    "ndvi": "NDVI原值指标",
                    "score": "标准化评分",
                }[method["operator"]],
            }
        ],
    }


def validate_outputs(manifest, data, root):
    expected = manifest["method"]["output_grid"]
    if [f["name"] for f in data["files"]] != [
        f["name"] for f in manifest["method"]["expected_outputs"]
    ]:
        raise Problem(422, "OUTPUT_CONTRACT", "本步处理结果不完整。")
    for item in data["files"]:
        path = (root / item["key"]).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            raise Problem(422, "OUTPUT_CONTRACT", "本步处理结果文件缺失。")
        with path.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != item["sha256"]:
                raise Problem(422, "OUTPUT_CONTRACT", "本步处理结果校验失败。")
        with rasterio.open(path) as ds:
            if grid(ds) != expected or ds.count != 1 or ds.dtypes[0] != "float64":
                raise Problem(422, "OUTPUT_CONTRACT", "本步处理结果的网格或数据类型错误。")
