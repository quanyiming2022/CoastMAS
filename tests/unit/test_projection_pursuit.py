import pytest

from coastmas.adapters.projection_pursuit import ProjectionPursuitAdapter
from coastmas.adapters.runtime import RunRequest
from coastmas.core.errors import CoastMASError


def request(tmp_path, **frame):
    return RunRequest(
        handler="ppci_mcdc",
        inputs={
            "frame": {
                "row_ids": ["a", "b", "c", "d"],
                "feature_names": ["distance"],
                "feature_units": ["m"],
                "values": [[0], [1], [9], [10]],
                "standardize": False,
                **frame,
            }
        },
        parameters={"clusters": 2, "seed": 42},
        work_root=tmp_path,
        timeout_seconds=30,
    )


def test_projection_rejects_bad_shapes_missing_science_and_unbounded_parameters(tmp_path):
    adapter = ProjectionPursuitAdapter(image="sha256:" + "a" * 64, docker="/usr/bin/docker")
    adapter.validate(request(tmp_path))
    for frame in (
        {"row_ids": ["a"] * 4},
        {"values": [[0], [1], [2]]},
        {"values": [[0], [1], [float("nan")], [2]]},
        {"feature_units": [""]},
        {"standardize": "false"},
    ):
        with pytest.raises(CoastMASError):
            adapter.validate(request(tmp_path, **frame))
    invalid = request(tmp_path)
    object.__setattr__(invalid, "parameters", {"clusters": 2.5, "seed": 42})
    with pytest.raises(CoastMASError):
        adapter.validate(invalid)


def test_regression_requires_response_and_explicit_unit(tmp_path):
    adapter = ProjectionPursuitAdapter(image="sha256:" + "a" * 64, docker="/usr/bin/docker")
    original = request(tmp_path)
    value = RunRequest(
        handler="ppr_ols",
        inputs=original.inputs,
        parameters={"terms": 1, "seed": 42},
        work_root=tmp_path,
        timeout_seconds=30,
    )
    with pytest.raises(CoastMASError, match="response"):
        adapter.validate(value)


def test_claiming_all_cells_requires_exact_observation_denominator(tmp_path):
    adapter = ProjectionPursuitAdapter(image="sha256:" + "a" * 64, docker="/usr/bin/docker")
    with pytest.raises(CoastMASError):
        adapter.validate(
            request(tmp_path, observation_scope="all_joint_valid_cells", joint_valid_cells=100)
        )
    with pytest.raises(CoastMASError):
        adapter.validate(request(tmp_path, observation_scope="sample_only"))
