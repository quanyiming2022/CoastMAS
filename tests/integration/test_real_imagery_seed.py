import base64
import hashlib
import json
from pathlib import Path

import numpy as np
from affine import Affine
from sqlalchemy.orm import Session

from coastmas.adapters.geofiles import Grid, encode_geotiff
from coastmas.core.validation import validate_workflow


def prepared_files(directory: Path):
    for number, name in enumerate(("yellow-river", "jiaozhou", "yangtze-2024", "yangtze-2025")):
        target = directory / name
        target.mkdir()
        transform = Affine(10, 0, 600000, 0, -10, 3500000)
        for band in ("red", "green", "nir"):
            values = np.full((4, 4), 0.2 if band != "nir" else 0.6 + 0.05 * number)
            values[0, 0] = np.nan
            (target / (band + ".tif")).write_bytes(
                encode_geotiff(Grid(values, "EPSG:32650", transform, "1"))
            )
        (target / "true-color.png").write_bytes(
            base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII="
            )
        )
        (target / "source-item.json").write_text(json.dumps({"id": "SYNTHETIC-TEST-" + name}))
        (target / "manifest.json").write_text(
            json.dumps(
                {
                    "calibration_policy": "stac_matches_cog_v1",
                    "item_id": "SYNTHETIC-TEST-" + name,
                    "source": "SYNTHETIC automated fixture, not public imagery",
                    "acquired_at": "2024-09-01T00:00:00Z"
                    if number == 2
                    else "2025-09-06T00:00:00Z",
                    "native_crs": "EPSG:32650",
                    "transform": list(transform)[:6],
                    "width": 4,
                    "height": 4,
                    "display_bounds_wgs84": [118.0, 31.6, 118.1, 31.7],
                    "files": {
                        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in target.iterdir()
                    },
                }
            )
        )


def test_real_imagery_seed_is_immutable_and_all_three_workflows_preflight(
    engine, actors, storage, tmp_path
):
    from coastmas.real_imagery import seed_real_imagery

    owner, _, _, project = actors
    prepared_files(tmp_path)
    with Session(engine) as session, session.begin():
        seeded = seed_real_imagery(session, owner, project, storage, tmp_path)
    assert len(seeded.scenes) == len(seeded.workflows) == 3
    for key, graph in seeded.workflows.items():
        selected = [seeded.assets[ref.source.id] for ref in graph.input_bindings]
        report = validate_workflow(graph, list(seeded.catalog.models), selected, seeded.scenes[key])
        assert report.valid, report.issues
    with Session(engine) as session, session.begin():
        again = seed_real_imagery(session, owner, project, storage, tmp_path)
    assert seeded.scenes == again.scenes
    change = seeded.assets[f"imagery:{project}:yangtze:observations"]
    assert change.time_resolution != "instantaneous"
    assert change.quality["acquisition_count"] == 2
    assert change.quality["continuous_temporal_coverage"] is False
