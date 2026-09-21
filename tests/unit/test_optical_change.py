from copy import deepcopy

import pytest

from coastmas.core.errors import ConstraintError
from tests.factories import scene


def inputs():
    grid = {
        "crs": "EPSG:32651",
        "transform": [10, 0, 400000, 0, -10, 3500000],
        "width": 2,
        "height": 1,
    }
    pair = {
        "frames": [
            {
                "acquired_at": "2024-09-01T00:00:00Z",
                "grid": grid,
                "nir": [[0.6, 0.8]],
                "red": [[0.2, None]],
                "source_item": "observed-2024",
            },
            {
                "acquired_at": "2025-09-06T00:00:00Z",
                "grid": grid,
                "nir": [[0.8, 0.8]],
                "red": [[0.2, 0.2]],
                "source_item": "observed-2025",
            },
        ]
    }
    context = scene(
        time_range={
            "start": pair["frames"][0]["acquired_at"],
            "end": pair["frames"][1]["acquired_at"],
        },
        data_policy={"study_area_crs": "EPSG:4326", "target_grid": grid},
    )
    return {"scene": context.model_dump(mode="json")}, {"observations": pair}


def test_change_uses_joint_valid_pixels_and_keeps_exact_acquisition_dates():
    from coastmas.domain.remote_sensing_components import vegetation_change

    context, data = inputs()
    result = vegetation_change(context, data, {})
    assert result["index"][0][0] == pytest.approx(0.1, abs=1e-12)
    assert result["index"][0][1] is None
    assert result["summary"]["valid_pixels"] == 1
    assert result["summary"]["acquisitions"] == ["2024-09-01T00:00:00Z", "2025-09-06T00:00:00Z"]
    assert result["summary"]["source_items"] == ["observed-2024", "observed-2025"]


@pytest.mark.parametrize("mismatch", ["grid", "date", "shape", "duplicate", "nonfinite"])
def test_change_rejects_unaligned_or_misdated_observations(mismatch):
    from coastmas.domain.remote_sensing_components import vegetation_change

    context, data = inputs()
    data = deepcopy(data)
    after = data["observations"]["frames"][1]
    if mismatch == "grid":
        after["grid"]["crs"] = "EPSG:32650"
    elif mismatch == "date":
        after["acquired_at"] = "2025-09-07T00:00:00Z"
    elif mismatch == "shape":
        after["nir"] = [[0.8]]
    elif mismatch == "duplicate":
        after["acquired_at"] = "2024-09-01T00:00:00Z"
    elif mismatch == "nonfinite":
        after["nir"][0][0] = float("inf")
    with pytest.raises((ConstraintError, ValueError)):
        vegetation_change(context, data, {})


def test_optical_preview_preserves_nodata_alpha_and_geographic_bounds():
    import base64

    import numpy as np
    from rasterio.io import MemoryFile

    from coastmas.core.contracts import TargetGridSpec
    from coastmas.domain.optical_preview import optical_preview

    grid = TargetGridSpec(
        crs="EPSG:4326", transform=[0.01, 0, 119, 0, -0.01, 38], width=2, height=2
    )
    preview = optical_preview(np.array([[-1, 1], [np.nan, 0]]), grid, "NDVI")
    assert preview["bounds"] == pytest.approx([119, 37.98, 119.02, 38])
    assert preview["minimum"] == -1 and preview["maximum"] == 1
    with MemoryFile(base64.b64decode(preview["url"].split(",", 1)[1])) as memory:
        with memory.open() as dataset:
            rgba = dataset.read()
    assert rgba.shape == (4, 2, 2)
    assert rgba[3, 1, 0] == 0
    assert rgba[3, 0, 0] == 255
    assert not np.array_equal(rgba[:3, 0, 0], rgba[:3, 0, 1])
