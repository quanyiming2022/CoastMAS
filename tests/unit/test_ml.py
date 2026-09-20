import numpy as np
import pytest

from coastmas.core.errors import ConstraintError
from coastmas.domain.ml import TrustedModelStore, train_forest


def dataset():
    features = np.array([[0, 0], [0, 0.1], [1, 0.9], [1, 1], [0, 0.05], [1, 0.95]])
    targets = np.array([0, 0, 1, 1, 0, 1])
    groups = ["train-a", "train-a", "train-b", "train-b", "test", "test"]
    return features, targets, groups


def test_classification_is_reproducible_and_group_split_is_explicit(tmp_path):
    features, targets, groups = dataset()
    first = train_forest(
        features, targets, groups, validation_groups={"test"}, task="classification", seed=42
    )
    second = train_forest(
        features, targets, groups, validation_groups={"test"}, task="classification", seed=42
    )
    np.testing.assert_equal(first.predictions, second.predictions)
    assert first.metrics["accuracy"] == 1
    assert set(first.training_groups).isdisjoint(first.validation_groups)
    assert len(first.feature_importance) == 2
    store = TrustedModelStore(tmp_path, b"a" * 32)
    identifier = store.save(first)
    loaded = store.load(identifier)
    np.testing.assert_equal(loaded.predict(features), first.estimator.predict(features))


def test_model_tampering_is_rejected_before_deserialization(tmp_path):
    features, targets, groups = dataset()
    trained = train_forest(
        features, targets, groups, validation_groups={"test"}, task="classification", seed=42
    )
    store = TrustedModelStore(tmp_path, b"b" * 32)
    identifier = store.save(trained)
    artifact = tmp_path / (identifier + ".joblib")
    artifact.write_bytes(b"untrusted altered model")
    with pytest.raises(ConstraintError, match="signature"):
        store.load(identifier)
    with pytest.raises(ConstraintError):
        store.load("../outside")


def test_empty_or_leaking_split_and_missing_values_block():
    features, targets, groups = dataset()
    with pytest.raises(ConstraintError):
        train_forest(
            features, targets, groups, validation_groups=set(), task="classification", seed=42
        )
    with pytest.raises(ConstraintError):
        train_forest(
            features, targets, groups, validation_groups=set(groups), task="classification", seed=42
        )
    features[0, 0] = np.nan
    with pytest.raises(ConstraintError):
        train_forest(
            features, targets, groups, validation_groups={"test"}, task="classification", seed=42
        )


def test_regression_reports_error_and_seed():
    trained = train_forest(
        [[0], [1], [2], [3], [1.5]],
        [0, 1, 2, 3, 1.5],
        ["a", "a", "b", "b", "test"],
        validation_groups={"test"},
        task="regression",
        seed=7,
    )
    assert trained.metrics["rmse"] >= 0
    assert trained.seed == 7
    assert trained.metrics["r2"] is None
