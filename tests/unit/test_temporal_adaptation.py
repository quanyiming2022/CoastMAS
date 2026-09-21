from datetime import UTC, datetime, timedelta

import pytest

from coastmas.core.temporal_adaptation import TemporalRequest, adapt_time_series

START = datetime(2025, 1, 1, tzinfo=UTC)


def stamp(hours):
    return (START + timedelta(hours=hours)).isoformat()


def request(**changes):
    payload = {
        "variable": "air_temperature",
        "unit": "degC",
        "output_unit": "kelvin",
        "aggregation_type": "intensive",
        "support": "interval",
        "method": "mean",
        "window_start": stamp(0),
        "window_end": stamp(4),
        "nodata_policy": "propagate",
        "observations": [
            {"start": stamp(0), "end": stamp(1), "value": 10},
            {"start": stamp(1), "end": stamp(4), "value": 20},
        ],
    }
    payload.update(changes)
    return TemporalRequest.model_validate(payload)


def test_duration_weighted_interval_mean_preserves_units_and_support():
    result = adapt_time_series(request())
    assert result.value == pytest.approx(290.65, abs=1e-12)
    assert result.observations_used == 2
    assert result.valid_observations == 2
    assert result.start == START and result.end == START + timedelta(hours=4)
    assert result.unit == "kelvin" and result.method == "mean"


def test_interval_totals_sum_once_and_never_allow_temperature_style_mean():
    result = adapt_time_series(
        request(
            variable="precipitation_amount",
            unit="mm",
            output_unit="m",
            aggregation_type="extensive",
            method="sum",
        )
    )
    assert result.value == pytest.approx(0.03, abs=1e-12)
    with pytest.raises(ValueError, match="aggregation"):
        request(aggregation_type="extensive", method="mean")


def test_point_interpolation_is_bounded_and_missing_neighbours_are_not_filled():
    observations = [
        {"start": stamp(0), "end": stamp(0), "value": 0},
        {"start": stamp(4), "end": stamp(4), "value": 20},
    ]
    point = request(
        support="point",
        window_start=None,
        window_end=None,
        method="interpolation",
        target_time=stamp(2),
        observations=observations,
    )
    assert adapt_time_series(point).value == pytest.approx(283.15, abs=1e-12)
    observations[1]["value"] = None
    missing = point.model_copy(
        update={
            "observations": request(
                support="point",
                method="nearest",
                window_start=None,
                window_end=None,
                target_time=stamp(4),
                observations=observations,
            ).observations
        }
    )
    assert adapt_time_series(missing).value is None
    assert adapt_time_series(missing).valid_observations == 1
    with pytest.raises(ValueError, match="extrapolation"):
        adapt_time_series(point.model_copy(update={"target_time": START + timedelta(hours=5)}))


def test_gaps_partial_intervals_overlap_and_missing_values_do_not_forge_coverage():
    with pytest.raises(ValueError, match="partition"):
        adapt_time_series(request(window_start=stamp(0.5)))
    with pytest.raises(ValueError, match="partition"):
        adapt_time_series(
            request(
                observations=[
                    {"start": stamp(0), "end": stamp(1), "value": 1},
                    {"start": stamp(2), "end": stamp(4), "value": 2},
                ]
            )
        )
    with pytest.raises(ValueError, match="overlap"):
        request(
            observations=[
                {"start": stamp(0), "end": stamp(2), "value": 1},
                {"start": stamp(1), "end": stamp(4), "value": 2},
            ]
        )
    payload = request().model_dump(mode="json")
    payload["observations"][1]["value"] = None
    missing = TemporalRequest.model_validate(payload)
    assert adapt_time_series(missing).value is None
    with pytest.raises(ValueError, match="NoData"):
        adapt_time_series(missing.model_copy(update={"nodata_policy": "reject"}))


@pytest.mark.parametrize(("method", "expected"), [("min", 10), ("max", 20)])
def test_extrema_are_of_observed_support_values(method, expected):
    result = adapt_time_series(request(method=method, output_unit="degC"))
    assert result.value == expected
    assert "source support" in result.interpretation


def test_categorical_nearest_preserves_label_and_rejects_interpolation():
    payload = dict(
        variable="land_cover",
        unit="1",
        output_unit="1",
        aggregation_type="categorical",
        support="point",
        method="nearest",
        window_start=None,
        window_end=None,
        target_time=stamp(1),
        observations=[
            {"start": stamp(0), "end": stamp(0), "value": 2},
            {"start": stamp(2), "end": stamp(2), "value": 7},
        ],
    )
    assert adapt_time_series(request(**payload)).value == 2
    with pytest.raises(ValueError, match="aggregation"):
        request(**(payload | {"method": "interpolation"}))


def test_dst_offset_support_uses_elapsed_utc_not_local_clock_hours():
    frame = request(
        window_start="2025-03-09T01:00:00-05:00",
        window_end="2025-03-09T04:00:00-04:00",
        observations=[
            {"start": "2025-03-09T01:00:00-05:00", "end": "2025-03-09T03:00:00-04:00", "value": 10},
            {"start": "2025-03-09T03:00:00-04:00", "end": "2025-03-09T04:00:00-04:00", "value": 20},
        ],
    )
    assert adapt_time_series(frame).value == pytest.approx(288.15, abs=1e-12)


def test_total_overflow_is_explicitly_rejected():
    frame = request(
        unit="m",
        output_unit="m",
        aggregation_type="extensive",
        method="sum",
        observations=[
            {"start": stamp(0), "end": stamp(1), "value": 1e308},
            {"start": stamp(1), "end": stamp(4), "value": 1e308},
        ],
    )
    with pytest.raises(ValueError, match="overflow"):
        adapt_time_series(frame)


@pytest.mark.parametrize(
    "changes",
    [
        {"unit": "m", "output_unit": "kelvin"},
        {"method": "sum", "aggregation_type": "extensive"},
        {"window_start": None},
        {"window_end": stamp(0)},
        {"support": "point"},
        {"method": "nearest", "target_time": stamp(1)},
        {"observations": [{"start": stamp(2), "end": stamp(1), "value": 3}]},
        {"observations": [{"start": stamp(1), "end": stamp(1), "value": 3}]},
    ],
)
def test_incompatible_units_and_support_cannot_be_approved(changes):
    with pytest.raises(ValueError):
        request(**changes)


def point_frame(**changes):
    payload = dict(
        support="point",
        method="nearest",
        target_time=stamp(1),
        window_start=None,
        window_end=None,
        observations=[
            {"start": stamp(0), "end": stamp(0), "value": 10},
            {"start": stamp(4), "end": stamp(4), "value": 20},
        ],
    )
    payload.update(changes)
    return request(**payload)


@pytest.mark.parametrize(
    "changes",
    [
        {"target_time": None},
        {"window_start": stamp(0)},
        {"aggregation_type": "categorical", "unit": "m", "output_unit": "m"},
        {"aggregation_type": "categorical", "support": "interval"},
        {"method": "min", "window_start": stamp(0), "window_end": stamp(4)},
    ],
)
def test_point_targets_cannot_ignore_window_or_change_categorical_units(changes):
    with pytest.raises(ValueError):
        point_frame(**changes)


def test_exact_acquisition_and_point_extrema_use_only_real_observations():
    exact = adapt_time_series(point_frame(target_time=stamp(4)))
    assert exact.observations_used == 1 and exact.value == pytest.approx(293.15, abs=1e-12)
    points = point_frame(method="min", target_time=None, window_start=stamp(0), window_end=stamp(4))
    assert adapt_time_series(points).value == pytest.approx(283.15, abs=1e-12)
    with pytest.raises(ValueError, match="no observed"):
        adapt_time_series(
            point_frame(method="min", target_time=None, window_start=stamp(1), window_end=stamp(2))
        )
    with pytest.raises(ValueError, match="extrapolation"):
        adapt_time_series(request(window_end=stamp(5)))


def test_conversion_overflow_cannot_publish_nonfinite_result():
    frame = point_frame(
        unit="m",
        output_unit="cm",
        observations=[
            {"start": stamp(0), "end": stamp(0), "value": 1e308},
            {"start": stamp(4), "end": stamp(4), "value": 1e308},
        ],
    )
    with (
        pytest.warns(RuntimeWarning, match="overflow"),
        pytest.raises(ValueError, match="converted"),
    ):
        adapt_time_series(frame)


def test_runtime_rejects_scene_target_mismatch_before_publishing():
    from coastmas.core.errors import ConstraintError
    from coastmas.domain.adaptation_catalog import temporal_component
    from tests.factories import scene

    with pytest.raises(ConstraintError, match="scene time"):
        temporal_component(
            {"scene": scene().model_dump(mode="json")},
            {"request": request().model_dump(mode="json")},
            {},
        )
