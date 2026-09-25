"""Real-data display previews and standards-based result packages with provenance."""

import csv
import io
import json
import os
import tempfile
import zipfile
from pathlib import Path

import numpy as np
import rasterio
from fastapi import APIRouter, Request, Response
from fastapi.responses import FileResponse
from pyproj import Transformer
from rasterio.enums import ColorInterp, Resampling
from rasterio.vrt import WarpedVRT
from starlette.background import BackgroundTask

from .execution import Execution
from .intake import Intake
from .store import Problem


def raster_preview(path, classification=False):
    try:
        with rasterio.open(path) as source:
            if not source.crs:
                raise Problem(422, "PREVIEW_CRS", "文件缺少可信坐标系，不能放到地图上")
            if source.crs.is_geographic and not (
                -180 <= source.bounds.left <= source.bounds.right <= 180
                and -85.051 <= source.bounds.bottom <= source.bounds.top <= 85.051
            ):
                raise Problem(422, "PREVIEW_EXTENT", "源经纬度无效或超出网络地图投影范围")
            with WarpedVRT(source, crs="EPSG:3857", resampling=Resampling.nearest) as display:
                ratio = min(1, 768 / max(display.width, display.height))
                width, height = (
                    max(1, int(display.width * ratio)),
                    max(1, int(display.height * ratio)),
                )
                raw = display.read(1, out_shape=(height, width), masked=True)
                values = raw.data.astype(float) * source.scales[0] + source.offsets[0]
                mask = ~np.ma.getmaskarray(raw) & np.isfinite(values)
                valid = values[mask]
                if not len(valid):
                    raise Problem(422, "PREVIEW_EMPTY", "有界预览内没有有效像元")
                low, high = float(valid.min()), float(valid.max())
                rgba = np.zeros((4, height, width), dtype="uint8")
                if classification:
                    palette = np.array(
                        [
                            [0, 142, 150],
                            [232, 170, 56],
                            [92, 77, 162],
                            [169, 76, 92],
                            [52, 136, 90],
                            [208, 111, 53],
                        ],
                        dtype="uint8",
                    )
                    labels = np.unique(valid).astype(int)
                    for label in labels:
                        selected = mask & (values == label)
                        rgba[:3, selected] = palette[(label - 1) % len(palette), :, None]
                    legend = [
                        {
                            "value": int(label),
                            "label": f"类别 {label}",
                            "color": "#"
                            + "".join(f"{v:02x}" for v in palette[(label - 1) % len(palette)]),
                        }
                        for label in labels
                    ]
                else:
                    fraction = (
                        np.zeros_like(values) if high == low else (values - low) / (high - low)
                    )
                    fraction = np.where(mask, fraction, 0)
                    for band, stops in enumerate([[49, 27, 242], [54, 161, 214], [105, 170, 87]]):
                        rgba[band] = np.interp(fraction, [0, 0.5, 1], stops).astype("uint8")
                    legend = []
                rgba[3] = np.where(mask, 255, 0).astype("uint8")
                transformer = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
                b = display.bounds
                corners = [
                    transformer.transform(x, y)
                    for x, y in [
                        (b.left, b.top),
                        (b.right, b.top),
                        (b.right, b.bottom),
                        (b.left, b.bottom),
                    ]
                ]
                with rasterio.io.MemoryFile() as memory:
                    with memory.open(
                        driver="PNG", width=width, height=height, count=4, dtype="uint8"
                    ) as png:
                        png.write(rgba)
                        png.colorinterp = (
                            ColorInterp.red,
                            ColorInterp.green,
                            ColorInterp.blue,
                            ColorInterp.alpha,
                        )
                    data = memory.read()
                return {
                    "scope": "bounded_display_not_full_statistics",
                    "width": width,
                    "height": height,
                    "sampled_valid_pixels": int(mask.sum()),
                    "preview_minimum": low,
                    "preview_maximum": high,
                    "unit": source.units[0],
                    "coordinates": corners,
                    "legend": legend,
                    "resampling": "nearest",
                    "display_crs": "EPSG:3857",
                }, data
    except Problem:
        raise
    except (rasterio.errors.RasterioError, ValueError) as exc:
        raise Problem(
            422, "PREVIEW_UNAVAILABLE", "该资料不能生成具有可靠空间位置的栅格预览"
        ) from exc


def owned_result(store, actor, job_id):
    job = Execution(store).read_job(actor, job_id)
    if job["status"] != "succeeded":
        raise Problem(409, "RESULT_NOT_READY", "没有已完成的成果")
    path = store.settings.storage_root / job["output_key"]
    return job, json.loads(path.read_text()), path


def owned_file(store, job, item):
    path = (store.settings.storage_root / item["key"]).resolve()
    folder = (store.settings.storage_root / job["output_key"]).with_suffix("").resolve()
    if not path.is_relative_to(folder):
        raise Problem(500, "ARTIFACT_BOUNDARY", "成果路径与运行身份不一致")
    return path


def write_comparison(archive, data):
    columns = ["id", "left", "right", "difference", "unit", "difference_unit"]
    table = io.StringIO(newline="")
    writer = csv.writer(table)
    writer.writerow(columns)
    selection = data["mode"] == "constraint_sensitivity"
    for row in data["rows"]:
        row = {"difference_unit": row["unit"], **row}
        writer.writerow(
            [str(row[k]).lower() if isinstance(row[k], bool) else row[k] for k in columns]
        )
    archive.writestr("comparison.csv", table.getvalue().encode("utf-8-sig"))
    archive.writestr(
        "comparison.csv-metadata.json",
        json.dumps(
            {
                "@context": "http://www.w3.org/ns/csvw",
                "url": "comparison.csv",
                "dc:description": data["basis"] + " 差值为对照减基准。",
                "tableSchema": {
                    "columns": [
                        {
                            "name": k,
                            "datatype": "string"
                            if k in {"id", "unit", "difference_unit"}
                            else "boolean"
                            if selection and k in {"left", "right"}
                            else "double",
                        }
                        for k in columns
                    ],
                    "primaryKey": "id",
                },
            },
            ensure_ascii=False,
        ),
    )


def write_allocations(archive, data):
    """Export every candidate, preserving exclusion and unknown feasibility separately."""
    columns = ["id", "selected", "allowed", "benefit", "cost", "area", "ecological_cost", "risk"]
    text = io.StringIO(newline="")
    writer = csv.writer(text)
    writer.writerow(columns)
    for item in data["allocations"]:
        writer.writerow(
            [
                ""
                if item[key] is None
                else str(item[key]).lower()
                if isinstance(item[key], bool)
                else item[key]
                for key in columns
            ]
        )
    archive.writestr("allocations.csv", text.getvalue().encode("utf-8-sig"))
    archive.writestr(
        "allocations.csv-metadata.json",
        json.dumps(
            {
                "@context": "http://www.w3.org/ns/csvw",
                "url": "allocations.csv",
                "tableSchema": {
                    "columns": [
                        {
                            "name": key,
                            "datatype": "string"
                            if key == "id"
                            else "boolean"
                            if key in {"selected", "allowed"}
                            else "double",
                            "null": [""],
                            **({"titles": ["area", "Area (m^2)"]} if key == "area" else {}),
                        }
                        for key in columns
                    ],
                    "primaryKey": "id",
                },
            },
            ensure_ascii=False,
        ),
    )


def write_temporal(archive, data):
    row = {
        "variable": data["variable"],
        "method": data["method"],
        "calendar": data["calendar"],
        "start": data.get("start"),
        "end": data.get("end"),
        "target": data.get("target"),
        "value": data["value"],
        "unit": data["conversion"]["target_unit"],
        "observations": data["observations"],
        "covered_duration": data.get("covered_duration"),
        "duration_unit": data.get("duration_unit"),
        "time_axis_unit": data["time_axis_unit"],
        "scope": data["scope"],
        "approximate": data["adaptation"]["approximate"],
        "basis": data["adaptation"]["basis"],
    }
    text = io.StringIO(newline="")
    writer = csv.writer(text)
    writer.writerow(row)
    writer.writerow(
        [
            "" if item is None else str(item).lower() if isinstance(item, bool) else item
            for item in row.values()
        ]
    )
    archive.writestr("temporal.csv", text.getvalue().encode("utf-8-sig"))
    archive.writestr(
        "temporal.csv-metadata.json",
        json.dumps(
            {
                "@context": "http://www.w3.org/ns/csvw",
                "url": "temporal.csv",
                "tableSchema": {
                    "columns": [
                        {
                            "name": key,
                            "null": [""],
                            "datatype": "double"
                            if key in {"value", "covered_duration"}
                            else "integer"
                            if key == "observations"
                            else "boolean"
                            if key == "approximate"
                            else "string",
                        }
                        for key in row
                    ]
                },
            },
            ensure_ascii=False,
        ),
    )


def bundle(store, job, result, path, actor=None):
    work = store.settings.storage_root / "exports"
    work.mkdir(exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix="result-", suffix=".zip", dir=work)
    os.close(descriptor)
    output = Path(name)
    try:
        with zipfile.ZipFile(
            output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=1
        ) as archive:
            archive.write(path, "result.json")
            data = result["data"]
            if data.get("spatial_result") and data.get("operator") != "planning_units":
                archive.writestr(
                    "planning-units.geojson"
                    if data.get("operator") == "planning_units"
                    else "assessment.geojson"
                    if "scores" in data
                    else "allocation.geojson",
                    json.dumps(data["spatial_result"], ensure_ascii=False, allow_nan=False),
                )
            if data.get("type") == "FeatureCollection":
                archive.writestr(
                    "entities.geojson",
                    json.dumps(
                        {"type": "FeatureCollection", "features": data["features"]},
                        ensure_ascii=False,
                        allow_nan=False,
                    ),
                )
            if data.get("scope") in {"declared_interval", "declared_instant"}:
                write_temporal(archive, data)
            if data.get("scope") == "immutable_result_comparison":
                write_comparison(archive, data)
                from .comparison_tasks import read_input

                if actor is None:
                    raise Problem(403, "PERMISSION_DENIED", "下载原始比较成果需要有效项目身份。")
                for side, reference in zip(
                    ["left", "right"], result["manifest"]["comparison_inputs"], strict=True
                ):
                    _, _, raw = read_input(
                        store, actor, job["project_id"], reference["job_id"], reference
                    )
                    archive.writestr(f"inputs/{side}.json", raw)
            if "allocations" in data:
                write_allocations(archive, data)
            elif "row_ids" in data:
                columns = ["row_id"] + [
                    key
                    for key in ["cluster", "fitted", "residuals", "scores", "ranks"]
                    if key in data
                ]
                if data.get("locations") is not None:
                    columns += ["longitude", "latitude"]
                text = io.StringIO(newline="")
                writer = csv.writer(text)
                writer.writerow(columns)
                for index, row_id in enumerate(data["row_ids"]):
                    row = [row_id] + [
                        data[key][index]
                        for key in columns[1:]
                        if key not in {"longitude", "latitude"}
                    ]
                    if "longitude" in columns:
                        row += data["locations"][index]
                    writer.writerow(row)
                archive.writestr("observations.csv", text.getvalue().encode("utf-8-sig"))
                archive.writestr(
                    "observations.csv-metadata.json",
                    json.dumps(
                        {
                            "@context": "http://www.w3.org/ns/csvw",
                            "url": "observations.csv",
                            "tableSchema": {
                                "columns": [
                                    {
                                        "name": column,
                                        "datatype": "string" if column == "row_id" else "double",
                                    }
                                    for column in columns
                                ],
                                "primaryKey": "row_id",
                            },
                        },
                        ensure_ascii=False,
                    ),
                )
            for item in data.get("files", []):
                archive.write(
                    owned_file(store, job, item),
                    Path(item["name"]).name,
                    compress_type=zipfile.ZIP_STORED,
                )
            archive.writestr(
                "README.txt",
                (
                    "CoastMAS actual results\n"
                    "result.json preserves source hashes, frozen task, model "
                    "and scientific states.\n"
                    "observations.csv contains identified training/observation rows, "
                    "when present.\n"
                    "allocations.csv includes every candidate, original constraints and "
                    "selection; empty selection means no feasible solution. "
                    "Area is in m^2; other units are in result.json method_snapshot.\n"
                    "temporal.csv keeps source calendar and dates as strings; "
                    "do not reinterpret non-Gregorian dates as Gregorian dates.\n"
                    "Sample scope is never the full raster unless explicitly declared.\n"
                    "prediction.tif contains the declared predictor-valid domain and NoData.\n"
                    "Engineering success does not assert scientific validation.\n"
                ),
            )
        return output
    except BaseException:
        output.unlink(missing_ok=True)
        raise


def router(store):
    routes = APIRouter()

    @routes.get("/api/assets/{asset_id}/preview")
    def asset_metadata(asset_id: str, request: Request):
        asset = Intake(store).read_asset(request.state.actor["id"], asset_id)
        return raster_preview(store.settings.storage_root / asset["object_key"])[0]

    @routes.get("/api/assets/{asset_id}/preview.png")
    def asset_image(asset_id: str, request: Request):
        asset = Intake(store).read_asset(request.state.actor["id"], asset_id)
        return Response(
            raster_preview(store.settings.storage_root / asset["object_key"])[1],
            media_type="image/png",
        )

    @routes.get("/api/jobs/{job_id}/preview")
    def job_metadata(job_id: str, request: Request):
        job, result, _ = owned_result(store, request.state.actor["id"], job_id)
        files = result["data"].get("files", [])
        if not files:
            raise Problem(404, "RASTER_RESULT_REQUIRED", "当前成果没有完整栅格")
        return raster_preview(
            owned_file(store, job, files[0]), result["manifest"]["draft"]["purpose"] == "cluster"
        )[0]

    @routes.get("/api/jobs/{job_id}/preview.png")
    def job_image(job_id: str, request: Request):
        job, result, _ = owned_result(store, request.state.actor["id"], job_id)
        files = result["data"].get("files", [])
        if not files:
            raise Problem(404, "RASTER_RESULT_REQUIRED", "当前成果没有完整栅格")
        return Response(
            raster_preview(
                owned_file(store, job, files[0]),
                result["manifest"]["draft"]["purpose"] == "cluster",
            )[1],
            media_type="image/png",
        )

    @routes.get("/api/jobs/{job_id}/bundle")
    def result_bundle(job_id: str, request: Request):
        job, result, path = owned_result(store, request.state.actor["id"], job_id)
        package = bundle(store, job, result, path, request.state.actor["id"])
        return FileResponse(
            package,
            filename=f"coastmas-{job_id}.zip",
            media_type="application/zip",
            background=BackgroundTask(package.unlink),
        )

    return routes
