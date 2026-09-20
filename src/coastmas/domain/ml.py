"""Group-separated random forest demonstration and authenticated private persistence.

No imputation is inferred. The same raw feature schema is used for training
and inference. Importance describes fitted-model dependence, never causality.
"""

import hashlib
import hmac
import io
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol, cast
from uuid import uuid4

# Narrow third-party boundaries; model outputs are converted and validated explicitly.
import joblib  # type: ignore[import-untyped]
import numpy as np
from numpy.typing import ArrayLike
from sklearn.ensemble import (  # type: ignore[import-untyped]
    RandomForestClassifier,
    RandomForestRegressor,
)

from coastmas.core.errors import ConstraintError
from coastmas.core.numeric import FloatArray, finite_array


class ForestEstimator(Protocol):
    def predict(self, features: ArrayLike) -> FloatArray: ...


@dataclass(frozen=True)
class TrainedForest:
    estimator: ForestEstimator
    predictions: FloatArray
    metrics: dict[str, float | None]
    feature_importance: FloatArray
    training_groups: tuple[str, ...]
    validation_groups: tuple[str, ...]
    seed: int
    task: str


def train_forest(
    features: ArrayLike,
    targets: ArrayLike,
    groups: list[str],
    *,
    validation_groups: set[str],
    task: Literal["classification", "regression"],
    seed: int,
    trees: int = 64,
) -> TrainedForest:
    matrix = finite_array(features, 2, "ML features")
    labels = finite_array(targets, 1, "ML targets")
    if matrix.shape[0] != labels.size or labels.size != len(groups) or not all(groups):
        raise ConstraintError("feature, target and group rows must agree")
    if matrix.size > 5000000 or not 1 <= trees <= 500 or not 0 <= seed < 2**32:
        raise ConstraintError("ML demonstration resource or seed bounds exceeded")
    if not validation_groups or not validation_groups.issubset(set(groups)):
        raise ConstraintError("explicit existing validation groups required")
    validation = np.asarray([group in validation_groups for group in groups], dtype=np.bool_)
    training = ~validation
    if not training.any() or not validation.any():
        raise ConstraintError("training and validation groups must both be nonempty and disjoint")
    if task == "classification":
        if np.any(labels != np.floor(labels)) or np.unique(labels[training]).size < 2:
            raise ConstraintError(
                "classification requires integer classes and at least two train classes"
            )
        estimator = RandomForestClassifier(
            n_estimators=trees, max_depth=12, random_state=seed, n_jobs=1
        )
    elif task == "regression":
        estimator = RandomForestRegressor(
            n_estimators=trees, max_depth=12, random_state=seed, n_jobs=1
        )
    else:
        raise ConstraintError("unknown ML task")
    estimator.fit(matrix[training], labels[training])
    predictions = finite_array(estimator.predict(matrix[validation]), 1, "ML predictions")
    observed = labels[validation]
    metrics: dict[str, float | None]
    if task == "classification":
        metrics = {"accuracy": float(np.mean(predictions == observed))}
    else:
        residual = float(np.square(predictions - observed).sum())
        variance = float(np.square(observed - observed.mean()).sum())
        metrics = {
            "rmse": float(np.sqrt(residual / observed.size)),
            "r2": 1 - residual / variance if observed.size >= 2 and variance > 0 else None,
        }
    return TrainedForest(
        cast(ForestEstimator, estimator),
        predictions,
        metrics,
        finite_array(estimator.feature_importances_, 1, "feature importance"),
        tuple(sorted(set(groups) - validation_groups)),
        tuple(sorted(validation_groups)),
        seed,
        task,
    )


class TrustedModelStore:
    """Only this service can sign models; unsigned user uploads never reach joblib.load."""

    def __init__(self, root: Path, signing_key: bytes):
        if len(signing_key) < 32:
            raise ConstraintError("model signing key must contain at least 32 bytes")
        self.root = root.resolve()
        self.key = signing_key
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, trained: TrainedForest) -> str:
        identifier = uuid4().hex
        buffer = io.BytesIO()
        joblib.dump(trained.estimator, buffer, compress=3)
        payload = buffer.getvalue()
        if len(payload) > 128 * 1024 * 1024:
            raise ConstraintError("model artifact exceeds 128 MiB budget")
        signature = hmac.new(
            self.key, identifier.encode() + b"\0" + payload, hashlib.sha256
        ).hexdigest()
        artifact = self.root / (identifier + ".joblib")
        metadata = self.root / (identifier + ".signature")
        with artifact.open("xb") as output:
            output.write(payload)
        try:
            with metadata.open("x") as output:
                output.write(signature)
        except OSError:
            artifact.unlink()
            raise
        return identifier

    def load(self, identifier: str) -> ForestEstimator:
        if re.fullmatch(r"[a-f0-9]{32}", identifier) is None:
            raise ConstraintError("invalid trusted model identifier")
        artifact = self.root / (identifier + ".joblib")
        signature_file = self.root / (identifier + ".signature")
        if artifact.is_symlink() or signature_file.is_symlink():
            raise ConstraintError("model store does not accept symbolic links")
        if artifact.stat().st_size > 128 * 1024 * 1024:
            raise ConstraintError("model artifact exceeds size budget")
        payload = artifact.read_bytes()
        expected = hmac.new(
            self.key, identifier.encode() + b"\0" + payload, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, signature_file.read_text()):
            raise ConstraintError("model signature mismatch; refusing deserialization")
        # The authenticated bytes, not a re-opened filename, are deserialized (no TOCTOU swap).
        estimator = joblib.load(io.BytesIO(payload))
        if not isinstance(estimator, (RandomForestClassifier, RandomForestRegressor)):
            raise ConstraintError("authenticated artifact is not a supported forest")
        return cast(ForestEstimator, estimator)
