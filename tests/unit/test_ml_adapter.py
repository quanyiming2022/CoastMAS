import numpy as np
import pytest

from coastmas.adapters.ml import MLAdapter
from coastmas.adapters.runtime import RunRequest
from coastmas.core.errors import CoastMASError
from coastmas.domain.ml import TrustedModelStore


def test_ml_adapter_trains_and_reloads_authenticated_model_with_feature_schema(tmp_path):
    store = TrustedModelStore(tmp_path / "models", b"k" * 32)
    adapter = MLAdapter(store)
    inputs = {
        "features": [[0, 0], [0, 1], [1, 0], [1, 1], [0, 0.2], [1, 0.8]],
        "targets": [0, 0, 1, 1, 0, 1],
        "groups": ["A", "A", "B", "B", "C", "C"],
        "validation_groups": ["C"],
        "feature_names": ["elevation", "slope"],
    }
    trained = adapter.run(
        RunRequest(
            "forest_classification", inputs, {"seed": 42, "trees": 16}, tmp_path / "work", 20
        )
    ).outputs
    assert trained["training_groups"] == ["A", "B"]
    assert trained["validation_groups"] == ["C"]
    assert trained["feature_names"] == ["elevation", "slope"]
    predicted = adapter.run(
        RunRequest(
            "predict",
            {
                "model_id": trained["model_id"],
                "features": [[0, 0.2], [1, 0.8]],
                "feature_names": ["elevation", "slope"],
            },
            {},
            tmp_path / "work",
            20,
        )
    ).outputs
    np.testing.assert_array_equal(predicted["predictions"], trained["validation_predictions"])
    with pytest.raises(CoastMASError, match="feature"):
        adapter.run(
            RunRequest(
                "predict",
                {
                    "model_id": trained["model_id"],
                    "features": [[0, 0.2]],
                    "feature_names": ["slope", "elevation"],
                },
                {},
                tmp_path / "work",
                20,
            )
        )
    assert not list((tmp_path / "work").iterdir())


def test_ml_adapter_rejects_inferred_split_and_unknown_parameters(tmp_path):
    adapter = MLAdapter(TrustedModelStore(tmp_path / "models", b"k" * 32))
    with pytest.raises(CoastMASError):
        adapter.run(
            RunRequest(
                "forest_classification",
                {"features": [[1]], "targets": [0], "groups": ["A"], "feature_names": ["x"]},
                {},
                tmp_path / "work",
                10,
            )
        )
    with pytest.raises(CoastMASError):
        adapter.run(
            RunRequest(
                "predict",
                {"model_id": "a" * 32, "features": [[1]], "feature_names": ["x"]},
                {"unsafe": 1},
                tmp_path / "work",
                10,
            )
        )
