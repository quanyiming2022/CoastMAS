import numpy as np
import pytest

from coastmas.domain.remote_sensing import calibrate_reflectance, normalized_difference


def test_reflectance_uses_declared_scale_offset_and_keeps_zero_nodata_separate():
    values = calibrate_reflectance(
        np.array([[0, 1000, 3000]], dtype="uint16"), scale=0.0001, offset=-0.1, nodata=0
    )
    assert np.isnan(values[0, 0])
    assert values[0, 1] == pytest.approx(0)
    assert values[0, 2] == pytest.approx(0.2)


def test_normalized_difference_masks_invalid_reflectance_and_zero_denominators():
    result = normalized_difference(
        np.array([[0.6, 0, 0.2, -0.1, np.nan]]), np.array([[0.2, 0, 0, 0.2, 0.1]])
    )
    np.testing.assert_allclose(result[0, [0, 2]], [0.5, 1])
    assert np.isnan(result[0, [1, 3, 4]]).all()
    with pytest.raises(ValueError):
        normalized_difference(np.ones((2, 2)), np.ones((1, 2)))


def test_registered_index_component_preserves_georeference_and_actual_valid_count():
    from coastmas.domain.remote_sensing_catalog import remote_sensing_catalog
    from coastmas.domain.remote_sensing_components import vegetation_index
    from tests.factories import scene

    context = scene(
        data_policy={
            "study_area_crs": "EPSG:4326",
            "target_grid": {
                "crs": "EPSG:32650",
                "transform": [10, 0, 600000, 0, -10, 4200000],
                "width": 2,
                "height": 1,
            },
        }
    )
    result = vegetation_index(
        {"scene": context.model_dump(mode="json")}, {"nir": [[0.6, None]], "red": [[0.2, 0.2]]}, {}
    )
    assert result["index"][0][0] == pytest.approx(0.5)
    assert result["index"][0][1] is None
    assert result["summary"]["valid_pixels"] == 1
    assert result["summary"]["nodata_pixels"] == 1
    catalog = remote_sensing_catalog("test")
    assert len(catalog.models) == 3
    for model in catalog.models:
        assert catalog.registry.resolve(model)
        assert all(item.unit == "1" for item in model.inputs)


def test_declared_calibration_must_match_file_metadata_before_real_ingestion():
    from coastmas.domain.remote_sensing import calibrated_cog_reflectance

    raw = np.array([[0, 1000, 3000]], dtype="uint16")
    with pytest.raises(ValueError, match="calibration"):
        calibrated_cog_reflectance(
            raw, scale=0.0001, offset=-0.1, nodata=0, file_scale=1, file_offset=0, file_nodata=0
        )
    values = calibrated_cog_reflectance(
        raw, scale=0.0001, offset=-0.1, nodata=0, file_scale=0.0001, file_offset=-0.1, file_nodata=0
    )
    assert np.isnan(values[0, 0])
    np.testing.assert_allclose(values[0, 1:], [0, 0.2], atol=1e-12)
    with pytest.raises(ValueError, match="calibration"):
        calibrated_cog_reflectance(
            raw,
            scale=0.0001,
            offset=-0.1,
            nodata=0,
            file_scale=0.0001,
            file_offset=-0.1,
            file_nodata=65535,
        )
