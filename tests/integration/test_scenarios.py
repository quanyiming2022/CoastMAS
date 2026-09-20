import hashlib
import json

import numpy as np
import pytest

from coastmas.adapters.geofiles import decode_geotiff
from coastmas.core.errors import CoastMASError
from coastmas.domain.samples import generate_samples
from coastmas.domain.scenarios import run_assessment_scenarios, run_screening_scenario


def test_synthetic_files_and_three_scientific_scenarios(tmp_path):
    data = tmp_path / "data"
    generate_samples(data)
    manifest = json.loads((data / "manifest.json").read_text())
    assert manifest["label"] == "SYNTHETIC / DEMONSTRATION DATA"
    for name, digest in manifest["sha256"].items():
        assert hashlib.sha256((data / name).read_bytes()).hexdigest() == digest
    result = run_screening_scenario(data, increment=0.5)
    assert result["inundated_area_m2"] == 80000
    assert result["estimated_affected_population"] == 320
    assert result["population_assumption"] == "uniform within each management unit"
    assert result["land_cover_area_m2"] == {"1": 40000.0, "2": 40000.0}
    assert result["units"]["U1"]["fraction"] == 1
    assert result["units"]["U2"]["fraction"] == 0
    baseline = run_screening_scenario(data, increment=0.0)
    assert baseline["inundated_area_m2"] == 40000
    assert baseline["estimated_affected_population"] == 160
    assessment = run_assessment_scenarios(data)
    np.testing.assert_allclose(assessment["scenario_b"]["scores"], [0.2, 0.4, 0.6, 0.8], atol=1e-12)
    np.testing.assert_allclose(assessment["scenario_c"]["change"], [0.2] * 4, atol=1e-12)
    np.testing.assert_allclose(assessment["scenario_c"]["trend_per_year"], [0.1] * 4, atol=1e-12)
    assert run_screening_scenario(data, increment=0.5) == result
    assert decode_geotiff((data / "dem.tif").read_bytes()).values.shape == (4, 4)


def test_scenarios_reject_tampered_inputs_instead_of_reusing_old_manifest(tmp_path):
    generate_samples(tmp_path)
    (tmp_path / "population.csv").write_text("unit_id,population\nU1,999999\n")
    with pytest.raises(CoastMASError, match="checksum"):
        run_screening_scenario(tmp_path, increment=0.5)


def test_sample_generator_does_not_overwrite_user_data(tmp_path):
    (tmp_path / "population.csv").write_text("user data")
    with pytest.raises(CoastMASError):
        generate_samples(tmp_path)
    assert (tmp_path / "population.csv").read_text() == "user data"
