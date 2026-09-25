"""Carry actual geometry into numeric results without inventing CSV locations."""

import math

from pydantic import Field, ValidationError
from pyproj import CRS
from pyproj.exceptions import CRSError

from .contracts import Contract
from .store import Problem
from .vector_view import display_geometry


class CoordinateReference(Contract):
    x_field: str = Field(min_length=1)
    y_field: str = Field(min_length=1)
    crs: str = Field(min_length=1)


def attach_coordinates(rows, asset, draft):
    declared = draft["options"].get("spatial_reference")
    if declared is None:
        return
    if asset["facts"]["profile"] not in {"csv", "csvw"}:
        raise Problem(
            422, "SPATIAL_REFERENCE", "坐标字段关联仅用于实际观测表；矢量直接读取文件定位"
        )
    try:
        reference = CoordinateReference.model_validate(declared)
        CRS.from_user_input(reference.crs)
        paths = {
            layer["name"] + "/" + field["name"]: field["name"]
            for layer in asset["facts"]["layers"]
            for field in layer["fields"]
        }
        if reference.x_field == reference.y_field:
            raise ValueError("Distinct axes required")
        x, y = paths[reference.x_field], paths[reference.y_field]
    except (ValidationError, ValueError, KeyError, CRSError) as exc:
        raise Problem(422, "SPATIAL_REFERENCE", "坐标字段或已声明坐标系无效，不能推测定位") from exc
    for row in rows:
        try:
            point = [float(row["properties"][x]), float(row["properties"][y])]
            if not all(math.isfinite(v) for v in point):
                raise ValueError("Nonfinite coordinate")
            native = {"type": "Point", "coordinates": point}
            geometry, issue = display_geometry(native, reference.crs)
            if issue:
                raise ValueError(issue)
        except (ValueError, TypeError, KeyError) as exc:
            raise Problem(
                422, "SPATIAL_REFERENCE", "已声明坐标关联包含缺失或无效位置", {"row": row["id"]}
            ) from exc
        row.update(geometry=native, geometry_crs=reference.crs)


def spatial_result(rows, manifest, properties):
    features, unavailable = [], []
    for row, calculated in zip(rows, properties, strict=True):
        if row.get("geometry") is None:
            continue
        geometry, issue = display_geometry(row["geometry"], row.get("geometry_crs"))
        if geometry is None:
            unavailable.append({"id": row["id"], "issue": issue})
            continue
        features.append(
            {
                "type": "Feature",
                "id": row["id"],
                "geometry": geometry,
                "properties": {
                    **calculated,
                    "source_properties": row["properties"],
                    "source_id": row["source_id"],
                },
            }
        )
    if not features:
        return {"spatial_unavailable": unavailable} if unavailable else {}
    return {
        "spatial_result": {
            "type": "FeatureCollection",
            "features": features,
            "source_asset_id": manifest["assets"][0]["id"],
            "source_sha256": manifest["assets"][0]["sha256"],
            "target_crs": "EPSG:4326",
            "theme_property": "assessment_score"
            if manifest["draft"]["purpose"] == "assessment"
            else "selected",
            "located_count": len(features),
            "observation_count": len(rows),
            "unlocated": unavailable,
        }
    }
