import numpy as np
import pytest
from affine import Affine

from coastmas.adapters.datasource import StoredDataResolver
from coastmas.adapters.geofiles import Grid, encode_geotiff
from coastmas.core.errors import CoastMASError
from coastmas.core.validation import validate_workflow
from tests.factories import asset, model, scene, variable, workflow


def test_real_stored_geotiff_binding_converts_units_and_preserves_nodata(storage):
    content = encode_geotiff(
        Grid(
            np.array([[100.0, np.nan], [200.0, 300.0]]),
            "EPSG:32650",
            Affine(10, 0, 500000, 0, -10, 3500000),
            "cm",
            "demo-datum",
        )
    )
    record = storage.put("dem/input.tif", content)
    dataset = asset(
        uri=record.uri,
        checksum=record.sha256,
        variables=(variable(unit="cm"),),
        spatial_extent={"west": 500000, "south": 3499980, "east": 500020, "north": 3500000},
        quality={
            "size_bytes": record.size,
            "spatial_resolution_m": 10,
            "geometry": "grid",
            "validated": True,
        },
    )
    report = validate_workflow(workflow(), [model()], [dataset], scene())
    assert report.valid
    result = StoredDataResolver(storage).resolve(dataset, variable(), report.bindings[0], scene())
    assert result == [[1.0, None], [2.0, 3.0]]
    corrupted = dataset.model_copy(update={"checksum": "0" * 64})
    with pytest.raises(CoastMASError, match="checksum"):
        StoredDataResolver(storage).resolve(corrupted, variable(), report.bindings[0], scene())


def test_stored_geotiff_metadata_cannot_be_overridden_by_catalog(storage):
    content = encode_geotiff(
        Grid(
            np.ones((2, 2)),
            "EPSG:32650",
            Affine(10, 0, 500000, 0, -10, 3500000),
            "m",
            "wrong-datum",
        )
    )
    record = storage.put("dem/input.tif", content)
    dataset = asset(uri=record.uri, checksum=record.sha256, quality={"size_bytes": record.size})
    with pytest.raises(CoastMASError, match="datum"):
        StoredDataResolver(storage).resolve(
            dataset, variable(), workflow().input_bindings[0], scene()
        )


def test_resolver_refuses_arbitrary_remote_urls(storage):
    with pytest.raises(CoastMASError, match="storage"):
        StoredDataResolver(storage).resolve(
            asset(uri="http://127.0.0.1/private"), variable(), workflow().input_bindings[0], scene()
        )


@pytest.mark.parametrize("format", ["CSV", "NetCDF"])
def test_real_tabular_files_resolve_all_values_and_convert_units(storage, tmp_path, format):
    import netCDF4

    if format == "CSV":
        content = b"height\n100\n200\n300\n"
    else:
        path = tmp_path / "input.nc"
        with netCDF4.Dataset(path, "w") as dataset:
            dataset.createDimension("row", 3)
            values = dataset.createVariable("height", "f8", ("row",))
            values.units = "cm"
            values[:] = [100, 200, 300]
        content = path.read_bytes()
    record = storage.put("table/input", content)
    source = asset(
        format=format,
        type="table",
        uri=record.uri,
        checksum=record.sha256,
        variables=[variable(data_type="array", unit="cm")],
        quality={"size_bytes": record.size},
    )
    result = StoredDataResolver(storage).resolve(
        source, variable(data_type="array"), workflow().input_bindings[0], scene()
    )
    assert result == [1, 2, 3]


def test_vector_geometry_container_is_bound_with_its_verified_crs(storage):
    import json

    feature = {
        "type": "Feature",
        "properties": {"unit_id": "u1"},
        "geometry": {"type": "Point", "coordinates": [117, 30]},
    }
    content = json.dumps({"type": "FeatureCollection", "features": [feature]}).encode()
    record = storage.put("vector/input", content)
    target = variable(
        name="height",
        standard_name="management_units",
        data_type="json",
        unit="1",
        dimension="dimensionless",
    )
    source = asset(
        format="GeoJSON",
        type="vector",
        crs="EPSG:4326",
        uri=record.uri,
        checksum=record.sha256,
        variables=[target],
        quality={"size_bytes": record.size},
    )
    result = StoredDataResolver(storage).resolve(
        source, target, workflow().input_bindings[0], scene()
    )
    assert result["crs"] == "EPSG:4326"
    assert result["features"][0]["properties"]["unit_id"] == "u1"
    transformed = StoredDataResolver(storage).resolve(
        source,
        target,
        workflow()
        .input_bindings[0]
        .model_copy(update={"crs_transform": "EPSG:4326 -> EPSG:32650"}),
        scene(),
    )
    assert transformed["crs"] == "EPSG:32650"
    assert transformed["features"][0]["geometry"]["coordinates"][0] == pytest.approx(500000)


def test_catalog_cannot_misstate_measured_raster_resolution(storage):
    content = encode_geotiff(
        Grid(np.ones((2, 2)), "EPSG:32650", Affine(10, 0, 0, 0, -10, 20), "m", "demo-datum")
    )
    record = storage.put("dem/resolution.tif", content)
    source = asset(
        uri=record.uri,
        checksum=record.sha256,
        spatial_extent=None,
        quality={
            "size_bytes": record.size,
            "spatial_resolution_m": 50,
            "geometry": "grid",
            "validated": True,
        },
    )
    with pytest.raises(CoastMASError, match="resolution"):
        StoredDataResolver(storage).resolve(
            source, variable(), workflow().input_bindings[0], scene()
        )


def test_csv_container_keeps_unit_identifiers_and_declared_column_units(storage):
    content = b"unit_id,population\nU1,120\nU2,160\n"
    record = storage.put("population/input", content)
    target = variable(
        name="records",
        standard_name="management_population",
        data_type="json",
        unit="1",
        dimension="dimensionless",
    )
    source = asset(
        format="CSV",
        type="table",
        uri=record.uri,
        checksum=record.sha256,
        variables=[target],
        quality={"size_bytes": record.size, "column_units": {"population": "person"}},
    )
    binding = (
        workflow()
        .input_bindings[0]
        .model_copy(
            update={
                "target": workflow()
                .input_bindings[0]
                .target.model_copy(update={"variable": "records"})
            }
        )
    )
    result = StoredDataResolver(storage).resolve(source, target, binding, scene())
    assert result["rows"] == [
        {"unit_id": "U1", "population": "120"},
        {"unit_id": "U2", "population": "160"},
    ]
    assert result["column_units"]["population"] == "person"


def test_explicit_cubic_binding_reads_real_geotiff_and_keeps_fixed_target_grid(storage):
    grid = Grid(
        np.full((8, 8), 250.0),
        "EPSG:32650",
        Affine(10, 0, 500000, 0, -10, 3500000),
        "cm",
        "demo-datum",
    )
    record = storage.put("cubic/input.tif", encode_geotiff(grid))
    source = asset(
        uri=record.uri,
        checksum=record.sha256,
        variables=(variable(unit="cm"),),
        spatial_extent={"west": 500000, "south": 3499920, "east": 500080, "north": 3500000},
        quality={"size_bytes": record.size, "spatial_resolution_m": 10},
    )
    context = scene(
        data_policy={
            "target_grid": {
                "crs": grid.crs,
                "transform": [20, 0, 500000, 0, -20, 3500000],
                "width": 4,
                "height": 4,
            }
        }
    )
    binding = (
        workflow()
        .input_bindings[0]
        .model_copy(update={"resampling": "cubic", "unit_conversion": "cm -> m"})
    )
    result = StoredDataResolver(storage).resolve(source, variable(), binding, context)
    np.testing.assert_allclose(result, np.full((4, 4), 2.5), rtol=0, atol=1e-12)
