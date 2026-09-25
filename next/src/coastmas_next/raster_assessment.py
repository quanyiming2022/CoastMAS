"""Global raster assessment: bounded I/O, shared global weights and ideal solutions.

Blocks are an I/O implementation detail, never independent fits or rankings.
Reference bounds, directions and unit declarations are fixed by the approved method.
"""

import hashlib
from contextlib import ExitStack

import numpy as np
import rasterio
from coastmas.core.contracts import UNITS
from coastmas.core.errors import ConstraintError
from coastmas.domain.assessment import normalize, normalized_weights
from rasterio.windows import Window

from .ahp import derive_weights
from .geospatial_view import band_check, data_mask, georeference
from .selection import selected_layer
from .store import Problem

BLOCK = 128
RASTERS = {"geotiff", "cog"}


def applicable(manifest):
    return any(a["facts"]["profile"] in RASTERS for a in manifest["assets"])


def inputs(settings, manifest, spec):
    sources = {a["id"]: a for a in manifest["assets"]}
    if any(a["facts"]["profile"] not in RASTERS for a in sources.values()):
        raise Problem(422, "RASTER_RELATION", "栅格与观测表须先通过明确空间关联，不能按行号混合")
    bindings = {}
    for binding in manifest["draft"]["mapping"]:
        if binding["role"] != "feature" or not binding.get("concept"):
            continue
        if binding["concept"] in bindings:
            raise Problem(422, "CONCEPT_AMBIGUOUS", "同一指标存在多个绑定，请明确来源")
        bindings[binding["concept"]] = binding
    result, grid = [], None
    for indicator in spec.indicators:
        binding = bindings.get(indicator.concept)
        if not binding or binding["asset_id"] not in sources:
            raise Problem(
                422,
                "CONCEPT_MAPPING_REQUIRED",
                "请补充方法所需指标的实际波段映射",
                {"concept": indicator.concept},
            )
        source = sources[binding["asset_id"]]
        layer = selected_layer(source, manifest["draft"])
        native = next(
            (f for f in layer["fields"] if layer["name"] + "/" + f["name"] == binding["field"]),
            None,
        )
        if native is None or not native.get("band"):
            raise Problem(422, "BINDING_INVALID", "指标绑定不是实际波段")
        with rasterio.open(settings.storage_root / source["object_key"]) as ds:
            band_check(ds, native["band"])
            location, _, issue = georeference(ds)
            if location != "located":
                raise Problem(422, "SPATIAL_LOCATION", issue)
            current = (ds.width, ds.height, ds.crs, ds.transform)
            if grid is not None and current != grid:
                raise Problem(
                    422, "GRID_ALIGNMENT_REQUIRED", "指标原生网格不同，需先明确统一网格与重采样规则"
                )
            grid = current
            unit = ds.units[native["band"] - 1] or binding.get("unit")
            if not unit:
                raise Problem(
                    422, "UNIT_REQUIRED", "实际指标缺少单位依据", {"concept": indicator.concept}
                )
            try:
                # Validated affine unit conversion applies after file scale and offset.
                converted = UNITS.Quantity(np.array([0.0, 1.0]), unit).to(indicator.unit).magnitude
            except Exception as exc:
                raise Problem(422, "UNIT_INCOMPATIBLE", "文件或声明单位与方法量纲不兼容") from exc
        result.append(
            {
                "source": source,
                "band": native["band"],
                "factor": float(converted[1] - converted[0]),
                "offset": float(converted[0]),
            }
        )
    return result


def output_specs(spec):
    result = [("comprehensive-index.tif", "composite", "综合评价结果", "float64")]
    for index, indicator in enumerate(spec.indicators, 1):
        result.extend(
            [
                (
                    f"raw-indicator-{index}.tif",
                    "raw_indicator",
                    f"原值指标 · {indicator.concept}",
                    "float64",
                ),
                (
                    f"indicator-{index}.tif",
                    "indicator",
                    f"标准化指标 · {indicator.concept}",
                    "float64",
                ),
                (
                    f"contribution-{index}.tif",
                    "contribution",
                    f"加权指标 · {indicator.concept}",
                    "float64",
                ),
            ]
        )
    return result + [("joint-validity.tif", "quality", "共同有效范围（质量）", "uint8")]


def compute(settings, manifest, spec, cancelled, artifact_dir):
    selected = inputs(settings, manifest, spec)

    def check_cancel():
        if cancelled.is_set():
            raise Problem(409, "CANCELLED", "运行已取消")

    with ExitStack() as stack:
        stack.enter_context(rasterio.Env(GDAL_CACHEMAX=64 * 1024**2))
        opened = {
            item["source"]["id"]: stack.enter_context(
                rasterio.open(settings.storage_root / item["source"]["object_key"])
            )
            for item in selected
        }
        reference = opened[selected[0]["source"]["id"]]

        def blocks():
            for row in range(0, reference.height, BLOCK):
                for column in range(0, reference.width, BLOCK):
                    check_cancel()
                    window = Window(
                        column,
                        row,
                        min(BLOCK, reference.width - column),
                        min(BLOCK, reference.height - row),
                    )
                    valid = np.ones((int(window.height), int(window.width)), dtype=bool)
                    arrays, masks = [], []
                    for item in selected:
                        value, mask = data_mask(
                            opened[item["source"]["id"]], item["band"], window=window
                        )
                        value = value * item["factor"] + item["offset"]
                        valid &= mask & np.isfinite(value)
                        arrays.append(value)
                        masks.append(mask & np.isfinite(value))
                    matrix = np.column_stack([value[valid] for value in arrays])
                    if len(matrix):
                        matrix = normalize(
                            matrix,
                            [i.lower for i in spec.indicators],
                            [i.upper for i in spec.indicators],
                            [i.positive for i in spec.indicators],
                        )
                    yield window, valid, matrix, arrays, masks

        count = 0
        totals = np.zeros(len(selected))
        squares = totals.copy()
        logs = totals.copy()
        lower = np.full(len(selected), np.inf)
        upper = -lower.copy()
        # One reduction over ALL joint-valid cells; never sampled or per-block training.
        for _, _, matrix, _, _ in blocks():
            if not len(matrix):
                continue
            count += len(matrix)
            totals += matrix.sum(axis=0)
            squares += (matrix**2).sum(axis=0)
            logarithms = np.zeros_like(matrix)
            np.log(matrix, out=logarithms, where=matrix > 0)
            logs += (matrix * logarithms).sum(axis=0)
            lower = np.minimum(lower, matrix.min(axis=0))
            upper = np.maximum(upper, matrix.max(axis=0))
        if not count:
            raise Problem(422, "NO_JOINT_VALID_CELLS", "所有必需指标无共同有效像元；不补零生成结果")
        if spec.method == "entropy":
            if count < 2:
                raise ConstraintError("entropy requires at least two valid cells")
            entropy = np.zeros_like(totals)
            positive = totals > 0
            entropy[positive] = (
                np.log(totals[positive]) - logs[positive] / totals[positive]
            ) / np.log(count)
            information = np.clip(1 - entropy, 0, 1)
            information[upper == lower] = 0
            if information.sum() <= np.finfo(float).eps:
                raise ConstraintError(
                    "no information in constant indicators; choose reviewed weights"
                )
            weights = information / information.sum()
        else:
            weights = normalized_weights([i.weight for i in spec.indicators], len(selected))
        norms = np.sqrt(squares)
        factors = np.divide(weights, norms, out=np.zeros_like(weights), where=norms > 0)
        best, worst = upper * factors, lower * factors
        artifact_dir.mkdir(parents=True, exist_ok=True)
        specs = output_specs(spec)
        targets = []
        for name, role, title, dtype in specs:
            ds = stack.enter_context(
                rasterio.open(
                    artifact_dir / name,
                    "w",
                    driver="GTiff",
                    width=reference.width,
                    height=reference.height,
                    count=1,
                    dtype=dtype,
                    crs=reference.crs,
                    transform=reference.transform,
                    nodata=None
                    if role == "quality"
                    else float("nan")
                    if role == "raw_indicator"
                    else -9999.0,
                    tiled=True,
                    blockxsize=256,
                    blockysize=256,
                    compress="deflate",
                    BIGTIFF="IF_SAFER",
                )
            )
            unit = (
                spec.indicators[int(name.split("-")[-1].split(".")[0]) - 1].unit
                if role == "raw_indicator"
                else "1"
            )
            ds.set_band_unit(1, unit)
            ds.set_band_description(1, title)
            ds.update_tags(
                method=spec.method,
                method_id=manifest["method"]["id"],
                method_revision=manifest["method"]["revision"],
                scope="full_grid",
                role=role,
            )
            targets.append(ds)
        minimum, maximum, total, sum_square = np.inf, -np.inf, 0.0, 0.0
        histogram = np.zeros(20, dtype="int64")
        for window, valid, matrix, arrays, masks in blocks():
            targets[-1].write(valid.astype("uint8"), 1, window=window)
            if spec.method == "topsis":
                contribution = matrix * factors
                d_best = np.linalg.norm(contribution - best, axis=1)
                d_worst = np.linalg.norm(contribution - worst, axis=1)
                denominator = d_best + d_worst
                if np.any(denominator <= np.finfo(float).eps):
                    raise ConstraintError(
                        "degenerate TOPSIS ideal solutions; no defensible ranking"
                    )
                scores = d_worst / denominator
            else:
                contribution = matrix * weights
                scores = contribution.sum(axis=1)

            def write_values(target, column, mask, current_window=window):
                image = np.full(mask.shape, target.nodata, dtype="float64")
                image[mask] = column
                target.write(image, 1, window=current_window)

            write_values(targets[0], scores, valid)
            for index, indicator in enumerate(spec.indicators):
                mask = masks[index]
                original = arrays[index][mask]
                write_values(targets[1 + 3 * index], original, mask)
                individual = (
                    normalize(
                        original[:, None],
                        [indicator.lower],
                        [indicator.upper],
                        [indicator.positive],
                    )[:, 0]
                    if len(original)
                    else original
                )
                write_values(targets[2 + 3 * index], individual, mask)
                write_values(targets[3 + 3 * index], contribution[:, index], valid)
            if len(scores):
                minimum = min(minimum, float(scores.min()))
                maximum = max(maximum, float(scores.max()))
                total += float(scores.sum())
                sum_square += float((scores**2).sum())
                histogram += np.histogram(scores, bins=20, range=(0, 1))[0]
        all_cells = reference.width * reference.height
    files = []
    for name, role, title, dtype in specs:
        path = artifact_dir / name
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        files.append(
            {
                "name": name,
                "title": title,
                "key": str(path.relative_to(settings.storage_root)),
                "sha256": digest,
                "size": path.stat().st_size,
                "role": role,
                "view_kind": "raster",
                "dtype": dtype,
            }
        )
    return {
        "scope": "full_grid",
        "files": files,
        "weights": weights.tolist(),
        "weight_evidence": (
            derive_weights(
                spec.weighting.labels,
                spec.weighting.matrix,
                [i.concept for i in spec.indicators],
                spec.weighting.consistency_limit,
            )
            if spec.weighting
            else {"method": spec.method, "scope": "full_grid"}
        ),
        "method_snapshot": manifest["method"],
        "business_validated": False,
        "contribution_meaning": "global_vector_normalized_weighted_coordinates"
        if spec.method == "topsis"
        else "additive_weighted_normalized_indicator",
        "statistics": {
            "total_pixels": all_cells,
            "valid_pixels": count,
            "invalid_pixels": all_cells - count,
            "scope": "full_grid",
            "minimum": minimum,
            "maximum": maximum,
            "mean": total / count,
            "standard_deviation": float(
                np.sqrt(max(0.0, sum_square / count - (total / count) ** 2))
            ),
            "histogram": {"edges": np.linspace(0, 1, 21).tolist(), "counts": histogram.tolist()},
        },
    }


def validate_outputs(manifest, data, root):
    from .decisions import AssessmentMethod

    expected = output_specs(
        AssessmentMethod.model_validate(manifest["method"]["spec"]["configuration"])
    )
    files = data.get("files", [])
    if [(f.get("name"), f.get("role"), f.get("dtype")) for f in files] != [
        (name, role, dtype) for name, role, _, dtype in expected
    ]:
        raise Problem(422, "OUTPUT_CONTRACT", "综合成果或必需过程图层缺失")
    facts = manifest["assets"][0]["facts"]
    for item in files:
        path = (root / item["key"]).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            raise Problem(422, "OUTPUT_CONTRACT", "成果文件缺失或越界")
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        with rasterio.open(path) as ds:
            valid = (
                ds.width == facts["width"]
                and ds.height == facts["height"]
                and ds.count == 1
                and ds.crs.to_string() == facts["crs"]
                and list(ds.transform)[:6] == facts["transform"]
                and ds.dtypes[0] == item["dtype"]
            )
        if not valid or digest != item["sha256"] or path.stat().st_size != item["size"]:
            raise Problem(422, "OUTPUT_CONTRACT", "成果字节、原生网格或类型与契约不一致")
    stats = data["statistics"]
    if (
        stats["total_pixels"] != facts["width"] * facts["height"]
        or stats["valid_pixels"] + stats["invalid_pixels"] != stats["total_pixels"]
        or sum(stats["histogram"]["counts"]) != stats["valid_pixels"]
    ):
        raise Problem(422, "OUTPUT_CONTRACT", "成果全域统计分母不一致")
