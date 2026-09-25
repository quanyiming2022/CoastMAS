import pytest
from pydantic import ValidationError

from coastmas.core.errors import ConstraintError
from coastmas.core.indicators import IndicatorFrameworkSpec
from coastmas.domain.indicator_frames import (
    IndicatorFrame,
    aggregate_frame,
    normalize_frame,
    temporal_change,
    weight_frame,
)
from coastmas.domain.indicator_framework import apply_framework


def framework(**changes):
    value = {
        "id": "framework-test",
        "name": "Explicit reference system",
        "version": 1,
        "description": "Synthetic validation framework",
        "demo": True,
        "spatial_support": "management_unit",
        "indicators": [
            {
                "indicator_id": "height",
                "name": "Height",
                "category": "Resource",
                "unit": "m",
                "direction": "positive",
                "source": {"x": "height_cm"},
                "formula": "x",
                "normalization": {"method": "fixed_minmax", "lower": 0, "upper": 2},
                "weight_method": "manual",
                "weight": 3,
            },
            {
                "indicator_id": "pressure",
                "name": "Pressure",
                "category": "Vulnerability",
                "unit": "1",
                "direction": "negative",
                "source": {"x": "pressure"},
                "formula": "x",
                "normalization": {"method": "fixed_minmax", "lower": 0, "upper": 1},
                "weight_method": "manual",
                "weight": 1,
            },
        ],
    }
    value.update(changes)
    return IndicatorFrameworkSpec.model_validate(value)


def observations():
    return IndicatorFrame.model_validate(
        {
            "unit_ids": ["U1", "U2"],
            "years": [2020, 2022],
            "columns": [
                {
                    "name": "pressure",
                    "unit": "1",
                    "reference_unit": "1",
                    "lower": 0,
                    "upper": 1,
                    "positive": True,
                },
                {
                    "name": "height_cm",
                    "unit": "cm",
                    "reference_unit": "cm",
                    "lower": 0,
                    "upper": 200,
                    "positive": True,
                },
            ],
            "values": [[[0, 0], [1, 100]], [[0, 100], [1, 200]]],
        }
    )


def test_framework_applies_names_units_direction_fixed_bounds_and_shared_weights():
    result = apply_framework(framework(), observations())
    assert result.unit_ids == ("U1", "U2")
    assert result.years == (2020, 2022)
    assert result.values == (((0, 0), (1, 1)), ((1, 0), (2, 1)))
    normalized = normalize_frame(result)
    weights = weight_frame(normalized, method="manual")
    scores = aggregate_frame(normalized, weights)
    assert scores.values == ((0.25, 0.375), (0.625, 0.75))
    change = temporal_change(scores)
    assert change.change == (0.375, 0.375)
    assert change.trend == (0.1875, 0.1875)
    assert change.ranks == ((2, 1), (2, 1))


@pytest.mark.parametrize(
    "mutation", ["duplicate", "mixed_weights", "zero_weights", "bounds", "unknown_unit", "alias"]
)
def test_framework_rejects_ambiguous_or_invalid_scientific_configuration(mutation):
    spec = framework().model_dump(mode="json")
    first, second = spec["indicators"]
    if mutation == "duplicate":
        second["indicator_id"] = first["indicator_id"]
    if mutation == "mixed_weights":
        second["weight_method"] = "entropy"
    if mutation == "zero_weights":
        first["weight"] = second["weight"] = 0
    if mutation == "bounds":
        first["normalization"]["upper"] = 0
    if mutation == "unknown_unit":
        first["unit"] = "unknown_coastmas_unit"
    if mutation == "alias":
        first["source"] = {"invalid alias": "height_cm"}
    with pytest.raises(ValidationError):
        IndicatorFrameworkSpec.model_validate(spec)


@pytest.mark.parametrize(
    "expression,unit",
    [("x + y", "m"), ('__import__("os")', "m"), ("x / 0", "m"), ("x", "s"), ("x * 10", "m")],
)
def test_formula_rejects_dimension_errors_unsafe_math_and_out_of_reference_values(expression, unit):
    spec = framework().model_dump(mode="json")
    indicator = spec["indicators"][0]
    indicator.update(formula=expression, unit=unit, source={"x": "height_cm", "y": "pressure"})
    with pytest.raises((ConstraintError, ValidationError)):
        apply_framework(IndicatorFrameworkSpec.model_validate(spec), observations())


def test_formula_can_use_multiple_columns_with_explicit_units():
    spec = framework().model_dump(mode="json")
    spec["indicators"][0].update(
        source={"height": "height_cm", "pressure": "pressure"}, formula="height * (1 - pressure)"
    )
    result = apply_framework(IndicatorFrameworkSpec.model_validate(spec), observations())
    assert result.values == (((0, 0), (0, 1)), ((1, 0), (0, 1)))
    spec["indicators"][0]["source"]["height"] = "missing"
    with pytest.raises(ConstraintError, match="column"):
        apply_framework(IndicatorFrameworkSpec.model_validate(spec), observations())


def test_unknown_observation_units_are_a_scientific_error():
    payload = observations().model_dump(mode="json")
    payload["columns"][1]["unit"] = "unknown_observation_unit"
    with pytest.raises(ConstraintError, match="unit"):
        apply_framework(framework(), IndicatorFrame.model_validate(payload))


def test_framework_accepts_prepared_raw_raster_observations_without_fake_reference_columns():
    from coastmas.adapters.projection_pursuit import ProjectionFrame

    raw = ProjectionFrame(
        row_ids=("r0c0", "r0c1", "r1c0", "r1c1"),
        feature_names=("pressure", "height_cm"),
        feature_units=("1", "cm"),
        values=((0, 0), (1, 100), (0, 100), (1, 200)),
        standardize=True,
        observation_scope="sample_only",
        joint_valid_cells=100,
    )
    result = apply_framework(framework(spatial_support="grid"), raw)
    assert result.unit_ids == raw.row_ids
    assert result.values == ((0, 0), (1, 1), (1, 0), (2, 1))
    assert result.years is None
    assert result.columns[0].lower == 0 and result.columns[0].upper == 2
