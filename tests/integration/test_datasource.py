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
    with pytest.raises(CoastMASError, match="metadata"):
        StoredDataResolver(storage).resolve(
            dataset, variable(), workflow().input_bindings[0], scene()
        )


def test_resolver_refuses_arbitrary_remote_urls(storage):
    with pytest.raises(CoastMASError, match="storage"):
        StoredDataResolver(storage).resolve(
            asset(uri="http://127.0.0.1/private"), variable(), workflow().input_bindings[0], scene()
        )
