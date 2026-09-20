import numpy as np
import pytest
from pydantic import ValidationError

from coastmas.core.errors import CoastMASError
from coastmas.domain.indicator_frames import (
    IndicatorFrame,
    aggregate_frame,
    normalize_frame,
    temporal_change,
    weight_frame,
)


def frame(periods=False):
    values = [[20, 80], [40, 60], [60, 40], [80, 20]]
    return IndicatorFrame.model_validate(
        {
            "unit_ids": ["U1", "U2", "U3", "U4"],
            "columns": [
                {
                    "name": "economic",
                    "unit": "1",
                    "reference_unit": "1",
                    "lower": 0,
                    "upper": 100,
                    "positive": True,
                    "weight": 1,
                },
                {
                    "name": "pressure",
                    "unit": "1",
                    "reference_unit": "1",
                    "lower": 0,
                    "upper": 100,
                    "positive": False,
                    "weight": 1,
                },
            ],
            "values": (
                [
                    values,
                    [[a + 10, b - 10] for a, b in values],
                    [[a + 20, b - 20] for a, b in values],
                ]
                if periods
                else values
            ),
            "years": [2020, 2021, 2022] if periods else None,
            "class_breaks": [0.25, 0.5, 0.75],
        }
    )


def test_fixed_reference_normalization_preserves_entity_ids_and_classification():
    normalized = normalize_frame(frame())
    weighted = weight_frame(normalized, method="manual")
    scores = aggregate_frame(normalized, weighted)
    assert scores.unit_ids == ("U1", "U2", "U3", "U4")
    np.testing.assert_allclose(scores.values, [[0.2, 0.4, 0.6, 0.8]])
    assert scores.classes == ((1, 2, 3, 4),)
    assert normalized.columns == ("economic", "pressure")


def test_three_period_frames_use_shared_reference_and_shared_weights():
    normalized = normalize_frame(frame(periods=True))
    scores = aggregate_frame(normalized, weight_frame(normalized, method="equal"))
    change = temporal_change(scores)
    np.testing.assert_allclose(change.change, [0.2] * 4)
    np.testing.assert_allclose(change.trend, [0.1] * 4)
    assert change.trend_unit == "1/year"
    assert change.unit_ids == scores.unit_ids


def test_column_units_convert_reference_bounds_before_normalization():
    source = frame().model_dump(mode="json")
    source["columns"][0].update(unit="cm", reference_unit="m", upper=1)
    normalized = normalize_frame(IndicatorFrame.model_validate(source))
    np.testing.assert_allclose(np.asarray(normalized.values)[0, :, 0], [0.2, 0.4, 0.6, 0.8])


def test_invalid_entity_alignment_or_incompatible_units_is_rejected():
    source = frame().model_dump(mode="json")
    source["unit_ids"][1] = "U1"
    with pytest.raises(ValidationError):
        IndicatorFrame.model_validate(source)
    source = frame().model_dump(mode="json")
    source["columns"][0]["reference_unit"] = "s"
    with pytest.raises(CoastMASError):
        normalize_frame(IndicatorFrame.model_validate(source))
    source = frame().model_dump(mode="json")
    source["values"][0][0] = None
    with pytest.raises(ValidationError):
        IndicatorFrame.model_validate(source)


def test_entropy_and_topsis_are_actual_computations_not_preset_scores():
    normalized = normalize_frame(frame())
    weighted = weight_frame(normalized, method="entropy")
    np.testing.assert_allclose(weighted, [0.5, 0.5])
    scores = aggregate_frame(normalized, weighted, method="topsis")
    np.testing.assert_allclose(scores.values, [[0, 1 / 3, 2 / 3, 1]])
