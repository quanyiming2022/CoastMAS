"""Domain inference preserves grid and uses one fitted model for every window."""

import threading

import numpy as np
import pytest
import rasterio
from coastmas_next.store import Problem
from rasterio.transform import from_origin


def grid(tmp_path, values, shift=0):
    path = tmp_path / f"grid-{len(list(tmp_path.glob('*.tif')))}.tif"
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=values.shape[1],
        height=values.shape[0],
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(110 + shift, 23, 0.01, 0.01),
        nodata=-9999,
    ) as ds:
        ds.write(values.astype("float32"), 1)
        ds.scales = (0.01,)
        ds.offsets = (2.0,)
        ds.set_band_unit(1, "m")
    return path


def test_windowed_training_retains_physical_values_and_complete_denominator(tmp_path):
    from coastmas_next.spatial_model import RasterInput, training_frame

    a = grid(tmp_path, np.arange(36).reshape(6, 6))
    b = grid(tmp_path, np.arange(36).reshape(6, 6) * 2)
    variables = [RasterInput(a, 1, "a", "m"), RasterInput(b, 1, "b", "m")]
    frame, metadata = training_frame(
        variables,
        scope="sample",
        sample_size=10,
        seed=42,
        standardize=True,
        response_index=None,
        cancelled=threading.Event(),
        window_size=3,
    )
    assert len(frame.values) == 10
    assert metadata["joint_valid_cells"] == 36
    assert frame.values[0][0] >= 2
    assert metadata["training_scope"] == "sample"
    assert frame.observation_scope == "sample_only"
    assert all(abs(v[1] - (2 * v[0] - 2)) < 1e-6 for v in frame.values)


def test_raster_identity_mismatch_is_rejected_without_resampling(tmp_path):
    from coastmas_next.spatial_model import RasterInput, training_frame

    a = grid(tmp_path, np.arange(16).reshape(4, 4))
    b = grid(tmp_path, np.arange(16).reshape(4, 4), shift=0.001)
    with pytest.raises(Problem, match="网格"):
        training_frame(
            [RasterInput(a, 1, "a", "m"), RasterInput(b, 1, "b", "m")],
            scope="all",
            sample_size=None,
            seed=0,
            standardize=False,
            response_index=None,
            cancelled=threading.Event(),
        )


def test_no_training_per_window_and_full_output_mask(tmp_path):
    from coastmas_next.spatial_model import RasterInput, apply_raster

    a = grid(tmp_path, np.array([[1, 2, -9999], [3, 4, 5]]))
    calls = []

    class FixedModel:
        def predict(self, values):
            calls.append(values.shape)
            return np.where(values[:, 0] > 2.03, 2, 1)

    output = tmp_path / "complete.tif"
    metadata = apply_raster(
        [RasterInput(a, 1, "a", "m")],
        FixedModel(),
        output,
        classification=True,
        cancelled=threading.Event(),
        window_size=2,
    )
    assert metadata["predicted_cells"] == 5
    assert len(calls) == 2
    with rasterio.open(output) as ds:
        assert ds.read(1).tolist() == [[1, 1, 0], [1, 2, 2]]
        assert int((ds.read_masks(1) > 0).sum()) == 5
        assert ds.crs.to_epsg() == 4326
