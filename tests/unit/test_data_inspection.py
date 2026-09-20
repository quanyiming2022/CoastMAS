import hashlib
import io
import json
import zipfile

import fiona
import netCDF4
import numpy as np
import pytest
from affine import Affine
from rasterio.io import MemoryFile
from rasterio.shutil import copy as raster_copy

from coastmas.adapters.geofiles import Grid, encode_geotiff
from coastmas.core.data_inspection import inspect_data
from coastmas.core.errors import CoastMASError
from tests.factories import asset, variable


def inspect(content, format, **changes):
    metadata = asset(
        spatial_extent=None, format=format, checksum=hashlib.sha256(content).hexdigest(), **changes
    )
    return inspect_data(content, metadata)


def test_geotiff_and_cog_are_inspected_from_real_bytes(tmp_path):
    content = encode_geotiff(
        Grid(
            np.array([[1.0, np.nan], [2.0, 3.0]]),
            "EPSG:32650",
            Affine(10, 0, 0, 0, -10, 20),
            "m",
            "demo-datum",
        )
    )
    report = inspect(content, "GeoTIFF")
    assert report.metadata["nodata_cells"] == 1
    assert report.metadata["cell_count"] == 4
    assert report.preview["values"][0][1] is None
    with MemoryFile(content) as source:
        path = tmp_path / "cog.tif"
        with source.open() as dataset:
            raster_copy(dataset, path, driver="COG")
        assert inspect(path.read_bytes(), "COG").metadata["layout"] == "COG"
    with pytest.raises(CoastMASError):
        inspect(content, "COG")
    with pytest.raises(CoastMASError):
        inspect(content, "GeoTIFF", crs="EPSG:4326")


def test_csv_and_json_validate_values_and_reject_duplicate_or_nonfinite_data():
    report = inspect(
        b"height,label\n1,a\n2,b\n", "CSV", type="table", variables=[variable(data_type="array")]
    )
    assert report.metadata["row_count"] == 2
    assert report.preview["rows"][1]["height"] == "2"
    assert (
        inspect(
            b'{"height":[1,2]}', "JSON", type="json", variables=[variable(data_type="array")]
        ).metadata["validated"]
        is True
    )
    for content in [b'{"height":1,"height":2}', b'{"height":[NaN]}']:
        with pytest.raises(CoastMASError):
            inspect(content, "JSON", type="json")
    for content in [b"height,height\n1,2\n", b"height\nInfinity\n"]:
        with pytest.raises(CoastMASError):
            inspect(content, "CSV", type="table")


def test_geojson_shapefile_and_geopackage_read_real_features(tmp_path):
    feature = {
        "type": "Feature",
        "properties": {"height": 2.0},
        "geometry": {"type": "Point", "coordinates": [117.0, 30.0]},
    }
    content = json.dumps({"type": "FeatureCollection", "features": [feature]}).encode()
    assert (
        inspect(content, "GeoJSON", type="vector", crs="EPSG:4326").metadata["feature_count"] == 1
    )
    schema = {"geometry": "Point", "properties": {"height": "float"}}
    for format, driver, extension in [
        ("Shapefile", "ESRI Shapefile", "shp"),
        ("GeoPackage", "GPKG", "gpkg"),
    ]:
        directory = tmp_path / format
        directory.mkdir()
        path = directory / ("data." + extension)
        with fiona.open(path, "w", driver=driver, crs="EPSG:4326", schema=schema) as collection:
            collection.write(feature)
        if format == "Shapefile":
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, "w") as archive:
                for item in directory.iterdir():
                    archive.writestr(item.name, item.read_bytes())
            content = stream.getvalue()
        else:
            content = path.read_bytes()
        report = inspect(content, format, type="vector", crs="EPSG:4326")
        assert report.metadata["feature_count"] == 1
        assert report.preview["features"][0]["properties"]["height"] == 2


def test_netcdf_checks_actual_units_shape_and_missing_values(tmp_path):
    path = tmp_path / "series.nc"
    with netCDF4.Dataset(path, "w") as dataset:
        dataset.createDimension("time", 3)
        values = dataset.createVariable("height", "f8", ("time",), fill_value=-999)
        values.units = "m"
        values[:] = [1, -999, 3]
    report = inspect(
        path.read_bytes(), "NetCDF", type="table", variables=[variable(data_type="array")]
    )
    assert report.preview["height"] == [1, None, 3]
    with pytest.raises(CoastMASError):
        inspect(
            path.read_bytes(),
            "NetCDF",
            type="table",
            variables=[variable(unit="cm", data_type="array")],
        )


def test_archive_traversal_and_checksum_mismatch_are_rejected():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("../escape.shp", b"x")
    with pytest.raises(CoastMASError):
        inspect(stream.getvalue(), "Shapefile", type="vector")
    with pytest.raises(CoastMASError, match="checksum"):
        inspect_data(b"{}", asset(format="JSON", type="json"))


def test_netcdf_infinity_is_not_silently_reclassified_as_nodata(tmp_path):
    path = tmp_path / "infinite.nc"
    with netCDF4.Dataset(path, "w") as dataset:
        dataset.createDimension("time", 1)
        values = dataset.createVariable("height", "f8", ("time",))
        values.units = "m"
        values[:] = [np.inf]
    with pytest.raises(CoastMASError):
        inspect(path.read_bytes(), "NetCDF", type="table")


def test_json_framework_preserves_per_indicator_metadata_instead_of_claiming_one_numeric_unit():
    payload = {
        "framework": {
            "columns": [{"name": "income", "unit": "USD", "positive": True}],
            "values": [[100], [200]],
        }
    }
    content = json.dumps(payload).encode()
    report = inspect(
        content,
        "JSON",
        type="json",
        variables=[
            variable(
                name="framework",
                standard_name="indicator_framework",
                data_type="json",
                unit="1",
                dimension="dimensionless",
            )
        ],
    )
    assert report.preview == payload


def test_concurrent_netcdf_bindings_preserve_complete_shape_without_parallel_native_io(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    from coastmas.core.data_inspection import read_data_value

    path = tmp_path / "concurrent.nc"
    with netCDF4.Dataset(path, "w") as dataset:
        dataset.createDimension("row", 20)
        values = dataset.createVariable("height", "f8", ("row",))
        values.units = "m"
        values[:] = np.arange(20)
    content = path.read_bytes()
    source = asset(format="NetCDF", type="table", checksum=hashlib.sha256(content).hexdigest())
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: read_data_value(content, source, "height"), range(12)))
    assert all(value == list(range(20)) for value in results)
