import copy

import pytest

from coastmas_next.result_views import coverage_statistics
from coastmas_next.store import Problem


def test_count_adapter_preserves_the_frozen_result_and_unknown_statistics():
    data = {"statistics": {"scope": "full_grid", "total_pixels": 8, "valid_pixels": 3}}
    frozen = copy.deepcopy(data)
    assert coverage_statistics(data)["invalid_pixels"] == 5
    assert data == frozen
    assert coverage_statistics({}) is None


@pytest.mark.parametrize("statistics", [
    {"scope": "sample", "total_pixels": 8, "valid_pixels": 3},
    {"scope": "full_grid", "total_pixels": 8, "valid_pixels": 9},
    {"scope": "full_grid", "total_pixels": 8, "valid_pixels": 3, "invalid_pixels": 0},
    {"scope": "full_grid", "total_pixels": 8},
])
def test_incomplete_or_inconsistent_statistics_are_not_silently_repaired(statistics):
    with pytest.raises(Problem) as error:
        coverage_statistics({"statistics": statistics})
    assert error.value.code == "RESULT_STATISTICS"
