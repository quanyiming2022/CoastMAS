import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from coastmas.core.errors import CoastMASError
from coastmas.core.raster_frame import RasterFeature, RasterFrameOptions, prepare_raster_frame


def raster(path, values, *, transform=None, crs="EPSG:32650"):
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=values.shape[1],
        height=values.shape[0],
        count=1,
        dtype="float32",
        nodata=-999,
        crs=crs,
        transform=transform or from_origin(300000, 2500000, 30, 30),
    ) as file:
        file.write(values.astype("float32"), 1)
    return path


def test_full_frame_keeps_zero_negative_values_and_common_mask_and_coordinates(tmp_path):
    a = raster(tmp_path / "a.tif", np.array([[0, -1, 2], [3, 4, -999]]))
    b = raster(tmp_path / "b.tif", np.array([[10, 11, -999], [13, 14, 15]]))
    result = prepare_raster_frame(
        [a, b],
        [RasterFeature(name="distance", unit="m"), RasterFeature(name="other", unit="m")],
        RasterFrameOptions(mode="all", standardize=False),
    )
    assert result["frame"]["values"] == [[0, 10], [-1, 11], [3, 13], [4, 14]]
    assert result["frame"]["row_ids"] == ["r0c0", "r0c1", "r1c0", "r1c1"]
    assert result["quality"]["joint_valid_cells"] == 4
    assert result["quality"]["excluded_cells"] == 2
    assert len(result["locations"]) == 4


def test_sampling_is_explicit_repeatable_and_counts_whole_intersection(tmp_path):
    path = raster(tmp_path / "large.tif", np.arange(11000).reshape(100, 110))
    features = [RasterFeature(name="distance", unit="m")]
    with pytest.raises(CoastMASError, match="10000"):
        prepare_raster_frame([path], features, RasterFrameOptions(mode="all", standardize=False))
    options = RasterFrameOptions(mode="sample", sample_size=50, seed=7, standardize=False)
    first = prepare_raster_frame([path], features, options)
    assert first == prepare_raster_frame([path], features, options)
    assert len(first["frame"]["values"]) == 50
    assert first["quality"]["joint_valid_cells"] == 11000
    assert first["quality"]["scope"] == "sample_only"


def test_wrong_crs_and_shifted_grids_are_not_stacked(tmp_path):
    values = np.arange(9).reshape(3, 3)
    a = raster(tmp_path / "a.tif", values)
    b = raster(tmp_path / "b.tif", values, transform=from_origin(300030, 2500000, 30, 30))
    features = [RasterFeature(name="a", unit="m"), RasterFeature(name="b", unit="m")]
    with pytest.raises(CoastMASError, match="grid"):
        prepare_raster_frame([a, b], features, RasterFrameOptions(mode="all", standardize=False))
    tn = raster(tmp_path / "tn.tif", values, crs="EPSG:4326")
    with pytest.raises(CoastMASError, match="coordinates"):
        prepare_raster_frame([tn], features[:1], RasterFrameOptions(mode="all", standardize=False))
