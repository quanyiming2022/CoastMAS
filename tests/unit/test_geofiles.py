import numpy as np
import pytest
from affine import Affine

from coastmas.adapters.geofiles import Grid, decode_geotiff, encode_geotiff, resample_grid
from coastmas.core.errors import CoastMASError


def test_real_geotiff_roundtrip_preserves_datum_units_and_nodata():
    grid = Grid(
        np.array([[1.0, np.nan], [3.0, 4.0]]),
        "EPSG:32650",
        Affine(30, 0, 500000, 0, -30, 3500000),
        "m",
        "synthetic-local-datum",
    )
    data = encode_geotiff(grid)
    assert data[:4] in (b"II*\x00", b"MM\x00*")
    restored = decode_geotiff(data)
    np.testing.assert_allclose(restored.values, grid.values, equal_nan=True)
    assert restored.vertical_datum == grid.vertical_datum
    assert restored.unit == "m"
    assert restored.cell_area_m2 == 900
    assert restored.transform == grid.transform


def test_decode_rejects_non_tiff_and_oversized_raster_before_allocation():
    with pytest.raises(CoastMASError):
        decode_geotiff(b"not a tiff")
    grid = Grid(np.ones((3, 3)), "EPSG:32650", Affine(10, 0, 1, 0, -10, 100), "m")
    with pytest.raises(CoastMASError, match="budget"):
        decode_geotiff(encode_geotiff(grid), max_cells=4)


def test_categorical_regridding_never_creates_fractional_classes():
    grid = Grid(
        np.array([[1.0, 2.0], [3.0, np.nan]]),
        "EPSG:32650",
        Affine(20, 0, 500000, 0, -20, 3500000),
        "dimensionless",
    )
    transformed = resample_grid(
        grid,
        crs="EPSG:32650",
        transform=Affine(10, 0, 500000, 0, -10, 3500000),
        shape=(4, 4),
        kind="categorical",
        method="nearest",
    )
    assert set(transformed.values[np.isfinite(transformed.values)]) == {1, 2, 3}
    assert np.isnan(transformed.values[-1, -1])
    with pytest.raises(CoastMASError, match="categorical"):
        resample_grid(
            grid,
            crs=grid.crs,
            transform=grid.transform,
            shape=(2, 2),
            kind="categorical",
            method="bilinear",
        )


def test_extensive_variables_cannot_be_interpolated_as_intensive():
    grid = Grid(np.ones((2, 2)), "EPSG:32650", Affine(10, 0, 1, 0, -10, 100), "person")
    with pytest.raises(CoastMASError, match="conservative"):
        resample_grid(
            grid,
            crs=grid.crs,
            transform=grid.transform,
            shape=(2, 2),
            kind="extensive",
            method="bilinear",
        )


def test_geographic_grid_cannot_report_degree_squared_as_square_metres():
    grid = Grid(np.ones((2, 2)), "EPSG:4326", Affine(0.1, 0, 120, 0, -0.1, 30), "m")
    with pytest.raises(CoastMASError, match="projected"):
        _ = grid.cell_area_m2


def test_invalid_grid_and_missing_metadata_fail_explicitly():
    for transform in (Affine(0, 0, 0, 0, 0, 0), Affine(float("nan"), 0, 0, 0, -1, 0)):
        with pytest.raises(CoastMASError):
            Grid(np.ones((2, 2)), "EPSG:32650", transform, "m")
    with pytest.raises(CoastMASError):
        Grid(np.array([[float("inf")]]), "EPSG:32650", Affine(1, 0, 1, 0, -1, 1), "m")


def test_extensive_grid_resampling_conserves_total_and_rejects_partial_coverage():
    source = Grid(
        np.array([[100.0]]), "EPSG:32650", Affine(20, 0, 500000, 0, -20, 3500000), "person"
    )
    target = resample_grid(
        source,
        crs=source.crs,
        transform=Affine(10, 0, 500000, 0, -10, 3500000),
        shape=(2, 2),
        kind="extensive",
        method="area_weighted",
    )
    np.testing.assert_allclose(target.values, [[25, 25], [25, 25]], rtol=0, atol=1e-10)
    assert target.values.sum() == source.values.sum()
    back = resample_grid(
        target,
        crs=source.crs,
        transform=source.transform,
        shape=(1, 1),
        kind="extensive",
        method="area_weighted",
    )
    np.testing.assert_allclose(back.values, source.values, rtol=0, atol=1e-10)
    with pytest.raises(CoastMASError, match="coverage"):
        resample_grid(
            source,
            crs=source.crs,
            transform=Affine(10, 0, 500000, 0, -10, 3500000),
            shape=(1, 1),
            kind="extensive",
            method="area_weighted",
        )


def test_cubic_continuous_regridding_preserves_linear_interior_and_unknown_cells():
    rows, columns = np.indices((16, 16))
    plane = 2 * (columns + 0.5) + 3 * (rows + 0.5)
    grid = Grid(plane, "EPSG:32650", Affine(10, 0, 500000, 0, -10, 3500000), "m")
    destination = Affine(20, 0, 500000, 0, -20, 3500000)
    result = resample_grid(
        grid, crs=grid.crs, transform=destination, shape=(8, 8), kind="continuous", method="cubic"
    )
    target_rows, target_columns = np.indices((8, 8))
    expected = 2 * (2 * target_columns + 1) + 3 * (2 * target_rows + 1)
    # Projected coordinates are ~3.5e6 m: budget eight coordinate ULPs,
    # converted through the 10 m cell size and the known plane gradient (2 + 3).
    coordinate_tolerance = 8 * np.spacing(3500000.0) / 10 * 5
    np.testing.assert_allclose(
        result.values[2:-2, 2:-2], expected[2:-2, 2:-2], rtol=0, atol=coordinate_tolerance
    )
    unknown = Grid(np.full((16, 16), np.nan), grid.crs, grid.transform, grid.unit)
    missing = resample_grid(
        unknown,
        crs=grid.crs,
        transform=destination,
        shape=(8, 8),
        kind="continuous",
        method="cubic",
    )
    assert np.isnan(missing.values).all()
    for kind in ("categorical", "extensive"):
        with pytest.raises(CoastMASError):
            resample_grid(
                grid, crs=grid.crs, transform=destination, shape=(8, 8), kind=kind, method="cubic"
            )
