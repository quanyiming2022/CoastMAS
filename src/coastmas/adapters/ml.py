"""Bounded scikit-learn training and authenticated joblib inference adapters."""

from functools import partial
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, JsonValue, TypeAdapter, ValidationError

from coastmas.adapters.runtime import Handler, PythonFunctionAdapter, RunRequest
from coastmas.core.errors import ConstraintError
from coastmas.core.numeric import finite_array
from coastmas.domain.ml import TrustedModelStore, train_forest

JSON_OUTPUT = TypeAdapter(dict[str, JsonValue])


class FeatureInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    features: list[list[float]] = Field(min_length=1, max_length=100000)
    feature_names: list[str] = Field(min_length=1, max_length=128)

    def check_schema(self) -> None:
        if not all(self.feature_names) or len(set(self.feature_names)) != len(self.feature_names):
            raise ConstraintError("feature names must be nonempty and unique")
        if any(len(row) != len(self.feature_names) for row in self.features):
            raise ConstraintError("feature matrix does not match its named columns")


class TrainingInput(FeatureInput):
    targets: list[float]
    groups: list[str]
    validation_groups: set[str]


class PredictionInput(FeatureInput):
    model_id: str = Field(pattern=r"^[a-f0-9]{32}$")


class TrainingOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    seed: int = Field(ge=0, lt=2**32)
    trees: int = Field(default=64, ge=1, le=500)


def train_model(
    store: TrustedModelStore,
    task: Literal["classification", "regression"],
    inputs: dict[str, JsonValue],
    parameters: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    data = TrainingInput.model_validate(inputs)
    options = TrainingOptions.model_validate(parameters)
    data.check_schema()
    trained = train_forest(
        data.features,
        data.targets,
        data.groups,
        validation_groups=data.validation_groups,
        task=task,
        seed=options.seed,
        trees=options.trees,
    )
    identifier = store.save(trained, feature_names=tuple(data.feature_names))
    return JSON_OUTPUT.validate_python(
        {
            "model_id": identifier,
            "feature_names": data.feature_names,
            "validation_predictions": trained.predictions.tolist(),
            "metrics": trained.metrics,
            "training_groups": list(trained.training_groups),
            "validation_groups": list(trained.validation_groups),
            "feature_importance": trained.feature_importance.tolist(),
            "seed": trained.seed,
            "importance_interpretation": "fitted model dependence; not causal attribution",
        }
    )


def predict_model(
    store: TrustedModelStore, inputs: dict[str, JsonValue], parameters: dict[str, JsonValue]
) -> dict[str, JsonValue]:
    if parameters:
        raise ConstraintError("prediction does not accept extra parameters")
    data = PredictionInput.model_validate(inputs)
    data.check_schema()
    estimator = store.load(data.model_id, feature_names=tuple(data.feature_names))
    result = finite_array(
        estimator.predict(np.asarray(data.features, dtype=np.float64)), 1, "predictions"
    )
    return JSON_OUTPUT.validate_python(
        {
            "predictions": result.tolist(),
            "model_id": data.model_id,
            "feature_names": data.feature_names,
        }
    )


class MLAdapter(PythonFunctionAdapter):
    def __init__(self, store: TrustedModelStore):
        handlers: dict[str, Handler] = {
            "forest_classification": partial(train_model, store, "classification"),
            "forest_regression": partial(train_model, store, "regression"),
            "predict": partial(predict_model, store),
        }
        super().__init__(handlers)

    def validate(self, request: RunRequest) -> None:
        super().validate(request)
        try:
            if request.handler == "predict":
                PredictionInput.model_validate(request.inputs).check_schema()
                if request.parameters:
                    raise ConstraintError("prediction does not accept extra parameters")
            else:
                TrainingInput.model_validate(request.inputs).check_schema()
                if any(isinstance(value, bool) for value in request.parameters.values()):
                    raise ConstraintError("ML integer options cannot be boolean")
                TrainingOptions.model_validate(request.parameters)
        except ValidationError as exc:
            fields: list[JsonValue] = [
                ".".join(str(part) for part in error["loc"])
                for error in exc.errors(include_input=False)
            ]
            raise ConstraintError("invalid ML input or options", {"fields": fields}) from exc
