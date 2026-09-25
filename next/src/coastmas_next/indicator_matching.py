"""Metadata-only AND/OR matching. Never identifies science from a filename or color."""

import hashlib
import itertools
import json

from sqlalchemy import select

from .intake import assets
from .resource_catalog import asset_metadata

ROLE_NAMES = {
    "red": "红光波段",
    "nir": "近红外波段",
    "blue": "蓝光波段",
    "green": "绿光波段",
    "swir1": "短波红外波段",
}


def project_assets(c, store, actor, project):
    store.permission(c, actor, project)
    recycled = select(asset_metadata.c.asset_id).where(asset_metadata.c.state == "recycled")
    return [
        dict(r)
        for r in c.execute(
            select(assets).where(assets.c.project_id == project, assets.c.id.not_in(recycled))
        ).mappings()
    ]


def fields(asset):
    return [f for layer in asset["facts"]["layers"] for f in layer["fields"]]


def role_bands(asset):
    roles = {}
    aliases = {"near_infrared": "nir", "near infrared": "nir", "shortwave_infrared": "swir1"}
    for f in fields(asset):
        if not f.get("band"):
            continue
        tags = f.get("metadata", {})
        role = str(tags.get("common_name") or f.get("description") or "").lower().strip()
        role = aliases.get(role, role)
        if role in ROLE_NAMES:
            roles.setdefault(role, []).append(f)
    return roles


def located(a):
    return bool(a["facts"].get("crs")) and not any(
        i["code"] in {"CRS_MISSING", "CRS_BOUNDS_CONFLICT", "LOCATION_CONFLICT"}
        for i in a["facts"].get("issues", [])
    )


def source_ref(a):
    return {"asset_id": a["id"], "revision": a["revision"], "sha256": a["sha256"]}


def candidate(mode, sources, bindings, label, status="ready", message=None):
    refs = [source_ref(a) for a in sources]
    key = hashlib.sha256(json.dumps([mode, refs, bindings], sort_keys=True).encode()).hexdigest()[
        :24
    ]
    return {
        "key": key,
        "mode": mode,
        "sources": refs,
        "bindings": bindings,
        "label": label,
        "status": status,
        "message": message,
    }


def match(definition, task, available):
    code = definition["indicator_id"]
    if definition["status"] != "published":
        return {
            "status": "not_installed",
            "message": "研发中：尚无已验证的生产实现",
            "missing": [],
            "candidates": [],
        }
    candidates, missing = [], []
    for a in available:
        for f in fields(a):
            concept = a["facts"].get("file_tags", {}).get("indicator_id")
            matches = concept == code or f.get("description") == definition["semantic_type"]
            if matches and f.get("band") and f.get("unit") == definition["unit"] and located(a):
                entry = candidate("existing", [a], {"band": f["band"]}, a["name"] + " · 已有指标")
                entry["key"] = f"existing:{a['id']}:{f['band']}"
                candidates.append(entry)
    family = definition["default_algorithm"]
    if family == "spectral":
        required = definition["input_roles"]
        partial = []
        for a in available:
            if a["facts"]["profile"] not in {"geotiff", "cog"}:
                continue
            roles = role_bands(a)
            partial.append([ROLE_NAMES[r] for r in required if r not in roles])
            if not all(len(roles.get(r, [])) == 1 for r in required):
                continue
            bindings = {r: roles[r][0]["band"] for r in required}
            # Identified spectral roles do not establish physical reflectance units.
            valid_units = all(
                roles[r][0].get("unit") in {"1", "reflectance"}
                and roles[r][0].get("metadata", {}).get("physical_quantity")
                == "surface_reflectance"
                for r in required
            )
            status = "ready" if valid_units and located(a) else "inapplicable"
            message = (
                None if status == "ready" else "影像定位或物理反射率依据不完整，请核对数据说明"
            )
            candidates.append(candidate("compute", [a], bindings, a["name"], status, message))
        missing = min(partial, key=len) if partial else [ROLE_NAMES[r] for r in required]
    elif family == "urban_speed":
        land = []
        for a in available:
            tags = a["facts"].get("file_tags", {})
            try:
                year = int(tags["observed_year"])
                classes = json.loads(tags["built_up_codes"])
                if (
                    1 <= year <= 9999
                    and classes
                    and all(type(v) is int for v in classes)
                    and located(a)
                ):
                    land.append((year, a, classes))
            except (KeyError, ValueError, TypeError):
                continue
        for first, last in itertools.combinations(
            sorted(land, key=lambda x: (x[0], x[1]["id"])), 2
        ):
            if first[0] == last[0]:
                continue
            a, b = first[1], last[1]
            same = all(
                a["facts"].get(k) == b["facts"].get(k)
                for k in ("crs", "width", "height", "transform")
            )
            candidates.append(
                candidate(
                    "compute",
                    [a, b],
                    {"years": [first[0], last[0]], "codes": [first[2], last[2]]},
                    f"{first[0]} {a['name']} → {last[0]} {b['name']}",
                    "ready" if same else "adaptation",
                    None if same else "两期网格不同，需要先按分类数据对齐；原始类别码保持不变",
                )
            )
        missing = ["第二期土地利用数据"] if land else ["两期具有年份及建设用地分类依据的数据"]
    elif family == "road_density":
        roads = []
        grids = [a for a in available if a["facts"]["profile"] in {"geotiff", "cog"} and located(a)]
        for a in available:
            for layer in a["facts"]["layers"]:
                if layer.get("geometry_type") not in {
                    "LineString",
                    "MultiLineString",
                } or not layer.get("crs"):
                    continue
                # OSM highway attribute or explicit source metadata establishes road semantics.
                if (
                    any(f["name"] == "highway" for f in layer["fields"])
                    or a["facts"].get("file_tags", {}).get("semantic_type") == "road"
                ):
                    roads.append((a, layer["name"]))
        for (a, layer), g in itertools.product(roads, grids):
            from pyproj import CRS

            crs = CRS(g["facts"]["crs"])
            projected_meters = crs.is_projected and all(
                x.unit_name == "metre" for x in crs.axis_info
            )
            candidates.append(
                candidate(
                    "compute",
                    [a, g],
                    {"road_layer": layer},
                    a["name"] + " · " + g["name"],
                    "ready" if projected_meters else "adaptation",
                    None if projected_meters else "统计窗口需要适用的米制分析网格",
                )
            )
        missing = ([] if roads else ["道路矢量（含道路类型依据）"]) + (
            [] if grids else ["统计参考网格"]
        )
    selected = {r["asset_id"] for r in task["draft"]["selection"]}
    ready = [c for c in candidates if c["status"] == "ready"]
    bound = [c for c in ready if all(s["asset_id"] in selected for s in c["sources"])]
    choices = bound or ready
    status = (
        "ready"
        if len(choices) == 1
        else "ambiguous"
        if len(choices) > 1
        else (candidates[0]["status"] if candidates else "missing")
    )
    chosen = choices[0]["key"] if len(choices) == 1 else None
    return {
        "status": status,
        "suggested_key": chosen,
        "candidates": candidates,
        "missing": missing if not candidates else [],
        "message": "当前数据满足，可以添加"
        if status == "ready"
        else "有多个适用来源，请选择"
        if status == "ambiguous"
        else candidates[0]["message"]
        if candidates
        else "还需要" + "、".join(missing),
    }
