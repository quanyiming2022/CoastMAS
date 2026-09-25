"""Result rendering resolves immutable run artifacts, never the task's input image."""

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import FileResponse

from .geospatial_view import InspectPoint, Views
from .outputs import owned_file, owned_result
from .store import Problem


def result_legend(result, item=None):
    if (item or {}).get("role") == "quality" or result["data"].get("operator") == "valid_mask":
        return [
            {"value": 0, "label": "所需指标无效", "color": "#e1e8ec"},
            {"value": 1, "label": "所需指标有效", "color": "#058f91"},
        ]
    if result["manifest"]["draft"]["purpose"] == "cluster":
        colors = ["#008e96", "#e8aa38", "#5c4da2", "#a94c5c", "#34885a", "#d06f35"]
        return [
            {"value": v, "label": f"类别 {v}", "color": colors[(v - 1) % len(colors)]}
            for v in range(1, int(result["manifest"]["draft"]["options"]["size"]) + 1)
        ]
    return []


def coverage_statistics(data):
    """Expose complete coverage counts without mutating the frozen computation result."""
    statistics = data.get("statistics")
    if statistics is None:
        return None
    result = dict(statistics)
    total, valid = result.get("total_pixels"), result.get("valid_pixels")
    if (
        result.get("scope") != "full_grid"
        or type(total) is not int
        or type(valid) is not int
        or not 0 <= valid <= total
    ):
        raise Problem(409, "RESULT_STATISTICS", "成果覆盖统计不完整或不一致，无法显示")
    invalid = total - valid
    if "invalid_pixels" in result and result["invalid_pixels"] != invalid:
        raise Problem(409, "RESULT_STATISTICS", "成果有效与无效像元数不一致")
    result["invalid_pixels"] = invalid
    return result


def router(store):
    routes = APIRouter()
    views = Views(store)

    def artifact(actor, job_id, index):
        job, result, _ = owned_result(store, actor, job_id)
        files = result["data"].get("files", [])
        if not 0 <= index < len(files):
            raise Problem(404, "ARTIFACT_UNAVAILABLE", "运行成果不可用")
        item = files[index]
        path = owned_file(store, job, item)
        if not path.is_file() or path.stat().st_size != item["size"]:
            raise Problem(409, "ARTIFACT_INTEGRITY", "成果缺失或大小改变，不能渲染")
        if path.suffix.lower() not in {".tif", ".tiff"}:
            raise Problem(422, "ARTIFACT_VIEW", "此成果不是栅格")
        return (
            {
                "id": f"{job_id}:{index}",
                "revision": 1,
                "sha256": item["sha256"],
                "object_key": item["key"],
                "facts": {"profile": "geotiff"},
                "render_palette": {
                    str(item["value"]): [int(item["color"][i : i + 2], 16) for i in (1, 3, 5)]
                    + [255]
                    for item in result_legend(result, item)
                },
            },
            path,
            item,
        )

    @routes.get("/api/jobs/{job_id}/descriptor")
    def descriptor(job_id: str, request: Request):
        _, result, _ = owned_result(store, request.state.actor["id"], job_id)
        outputs = []
        for index, item in enumerate(result["data"].get("files", [])):
            kind = "raster" if item["name"].lower().endswith((".tif", ".tiff")) else "file"
            outputs.append(
                {
                    "id": str(index),
                    "run_id": job_id,
                    "name": item["name"],
                    "title": item.get("title", item["name"]),
                    "role": item.get("role", "result"),
                    "view_kind": kind,
                    "legend": result_legend(result, item) if kind == "raster" else [],
                    "sha256": item["sha256"],
                    "size": item["size"],
                    "resource": f"/jobs/{job_id}/artifacts/{index}",
                }
            )
        return {
            "schema_version": 1,
            "run_id": job_id,
            "draft_revision": result["manifest"]["draft_revision"],
            "primary": next(
                (item for item in outputs if item["role"] == "composite"),
                next((item for item in outputs if item["view_kind"] == "raster"), None),
            ),
            "outputs": outputs,
            "statistics": coverage_statistics(result["data"])
            if any(o["view_kind"] == "raster" for o in outputs)
            else None,
            "vector_statistics": result["data"].get("statistics")
            if result["data"].get("spatial_result")
            else None,
            "business_validated": result["states"]["business_validated"],
        }

    @routes.get("/api/jobs/{job_id}/artifacts/{index}/view")
    def view(job_id: str, index: int, request: Request, band: int = Query(1, ge=1)):
        record, _, _ = artifact(request.state.actor["id"], job_id, index)
        return views.descriptor(record, band)

    @routes.get("/api/jobs/{job_id}/artifacts/{index}/view.png")
    def image(job_id: str, index: int, request: Request, band: int = Query(1, ge=1)):
        record, _, _ = artifact(request.state.actor["id"], job_id, index)
        views.descriptor(record, band)
        return Response(
            (views.cache(record, band) / "native.png").read_bytes(), media_type="image/png"
        )

    @routes.get("/api/jobs/{job_id}/artifacts/{index}/tiles/{z}/{x}/{y}.png")
    def tile(
        job_id: str,
        index: int,
        z: int,
        x: int,
        y: int,
        request: Request,
        band: int = Query(1, ge=1),
    ):
        record, _, _ = artifact(request.state.actor["id"], job_id, index)
        return Response(views.tile(record, band, z, x, y), media_type="image/png")

    @routes.post("/api/jobs/{job_id}/artifacts/{index}/inspect")
    def inspect(job_id: str, index: int, request: Request, body: InspectPoint):
        record, _, _ = artifact(request.state.actor["id"], job_id, index)
        return views.inspect(record, body)

    @routes.get("/api/jobs/{job_id}/artifacts/{index}/download")
    def download(job_id: str, index: int, request: Request):
        job, result, _ = owned_result(store, request.state.actor["id"], job_id)
        files = result["data"].get("files", [])
        if not 0 <= index < len(files):
            raise Problem(404, "ARTIFACT_UNAVAILABLE", "运行成果不可用")
        item = files[index]
        path = owned_file(store, job, item)
        from .asset_integrity import hash_file

        if (
            not path.is_file()
            or path.stat().st_size != item["size"]
            or hash_file(path) != item["sha256"]
        ):
            raise Problem(409, "ARTIFACT_INTEGRITY", "成果文件与固定版本不一致")
        media = (
            "image/tiff"
            if path.suffix.lower() in {".tif", ".tiff"}
            else "application/geo+json"
            if path.suffix.lower() == ".geojson"
            else "application/json"
            if path.suffix.lower() == ".json"
            else "application/octet-stream"
        )
        return FileResponse(path, filename=item["name"], media_type=media)

    return routes
