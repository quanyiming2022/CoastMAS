"""Deterministic tiny coastal dataset with independently hand-checkable results."""

import hashlib
import json
from pathlib import Path

import numpy as np
from affine import Affine
from pyproj import Transformer

from coastmas.adapters.geofiles import Grid, encode_geotiff
from coastmas.core.errors import CoastMASError

LABEL = "SYNTHETIC / DEMONSTRATION DATA"
CRS = "EPSG:32650"
DATUM = "synthetic-local-datum-v1"
TRANSFORM = Affine(100, 0, 500000, 0, -100, 3500000)


def generate_samples(directory: Path) -> None:
    names = {
        "coastal_aoi.geojson",
        "management_units.geojson",
        "dem.tif",
        "land_cover_t1.tif",
        "land_cover_t2.tif",
        "population.csv",
        "economic.csv",
        "tide.csv",
        "protection_zone.geojson",
        "manifest.json",
        "README.md",
    }
    if any((directory / name).exists() for name in names):
        raise CoastMASError(
            "IMMUTABLE_CONFLICT", "sample generation cannot overwrite existing data"
        )
    directory.mkdir(parents=True, exist_ok=True)
    to_lonlat = Transformer.from_crs(CRS, "EPSG:4326", always_xy=True)

    def feature(
        identifier: str, left: float, bottom: float, right: float, top: float
    ) -> dict[str, object]:
        coordinates = [
            list(to_lonlat.transform(x, y))
            for x, y in [(left, bottom), (right, bottom), (right, top), (left, top), (left, bottom)]
        ]
        return {
            "type": "Feature",
            "properties": {"unit_id": identifier, "label": LABEL},
            "geometry": {"type": "Polygon", "coordinates": [coordinates]},
        }

    def collection(name: str, features: list[dict[str, object]]) -> None:
        content = {"type": "FeatureCollection", "name": name, "label": LABEL, "features": features}
        (directory / name).write_text(json.dumps(content, sort_keys=True, indent=2) + "\n")

    collection("coastal_aoi.geojson", [feature("AOI", 500000, 3499600, 500400, 3500000)])
    collection(
        "management_units.geojson",
        [
            feature("U1", 500000, 3499800, 500200, 3500000),
            feature("U2", 500200, 3499800, 500400, 3500000),
            feature("U3", 500000, 3499600, 500200, 3499800),
            feature("U4", 500200, 3499600, 500400, 3499800),
        ],
    )
    collection("protection_zone.geojson", [feature("P1", 500200, 3499600, 500400, 3499800)])
    heights = np.tile(np.array([-0.2, 0.2, 0.7, 1.2]), (4, 1))
    classes = np.array(
        [[1.0, 1.0, 3.0, 3.0], [1.0, 1.0, 3.0, 3.0], [2.0, 2.0, 4.0, 4.0], [2.0, 2.0, 4.0, 4.0]]
    )
    for name, values, unit, datum in [
        ("dem.tif", heights, "m", DATUM),
        ("land_cover_t1.tif", classes, "dimensionless", None),
        ("land_cover_t2.tif", np.where(classes == 3, 4.0, classes), "dimensionless", None),
    ]:
        (directory / name).write_bytes(encode_geotiff(Grid(values, CRS, TRANSFORM, unit, datum)))
    (directory / "population.csv").write_text(
        "unit_id,population,label\n"
        + "".join(
            f"{identifier},{population},{LABEL}\n"
            for identifier, population in [("U1", 120), ("U2", 160), ("U3", 200), ("U4", 240)]
        )
    )
    (directory / "economic.csv").write_text(
        "unit_id,year,economic,pressure,label\n"
        + "".join(
            f"U{index},{2020 + period},{20 * index + 10 * period},"
            f"{100 - 20 * index - 10 * period},{LABEL}\n"
            for period in range(3)
            for index in range(1, 5)
        )
    )
    (directory / "tide.csv").write_text(
        f"time,level_m,vertical_datum,label\n2020-01-01T00:00:00Z,0,{DATUM},{LABEL}\n"
    )
    (directory / "README.md").write_text(
        f"# {LABEL}\n\n"
        "合成的 400m × 400m 区域，不代表真实地形、人口、潮位或行政单元。\n"
        "栅格 EPSG:32650，每格 100m；GeoJSON 为 WGS84。高程采用虚构的本地垂向基准，"
        "基准水位 0m。海侧种子位于西边界，4 邻接。人口在管理单元内均匀分布，"
        "受影响人口仅为面积比例估计。筛查不是水动力模拟。\n"
        "评价 economic 为正向、pressure 为负向，参考范围固定 [0,100]，等权。"
        "2020/2021/2022 三期，同一参考与权重，不做逐期归一化。\n"
    )
    hashes = {
        name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
        for name in sorted(names - {"manifest.json"})
    }
    manifest = {
        "label": LABEL,
        "schema_version": "1.0.0",
        "sha256": hashes,
        "baseline_m": 0.0,
        "vertical_datum": DATUM,
        "connectivity": 4,
        "seeds": [[0, 0], [1, 0], [2, 0], [3, 0]],
        "seed": 42,
    }
    (directory / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
