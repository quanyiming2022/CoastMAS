import pytest

from coastmas.core.decomposition import DecompositionRequest, decompose_model
from coastmas.core.errors import CoastMASError


def test_python_decomposition_is_static_and_preserves_call_dependencies(tmp_path):
    marker = tmp_path / "must-not-execute"
    source = f"""
from pathlib import Path
Path({str(marker)!r}).write_text("unsafe")
def preprocess_values(values):
    return values

def compute_score(values, weight=1):
    return preprocess_values(values) * weight

def validate_result(result):
    return result >= 0
"""
    result = decompose_model(DecompositionRequest(kind="python", name="score", source=source))
    assert not marker.exists()
    assert {item.stage for item in result.components} == {"preprocess", "compute", "validate"}
    assert result.dependencies == (("preprocess_values", "compute_score"),)
    assert result.review_required
    assert result.executable is False
    assert "top-level statements are not executed" in result.warnings


def test_black_box_is_atomic_and_cannot_be_silently_decomposed():
    result = decompose_model(DecompositionRequest(kind="black_box", name="external-hydrodynamic"))
    assert len(result.components) == 1
    assert result.components[0].atomic
    assert result.components[0].id == "external-hydrodynamic"
    assert result.dependencies == ()


def test_declared_pipeline_validates_references_and_rejects_cycles():
    components = [
        {"id": "prepare", "stage": "preprocess", "inputs": ["source"], "outputs": ["x"]},
        {"id": "solve", "stage": "compute", "inputs": ["x"], "outputs": ["result"]},
    ]
    result = decompose_model(
        DecompositionRequest(
            kind="pipeline", name="pipe", components=components, dependencies=[("prepare", "solve")]
        )
    )
    assert result.dependencies == (("prepare", "solve"),)
    with pytest.raises(CoastMASError, match="cycle"):
        decompose_model(
            DecompositionRequest(
                kind="declared",
                name="pipe",
                components=components,
                dependencies=[("prepare", "solve"), ("solve", "prepare")],
            )
        )
    with pytest.raises(CoastMASError, match="unknown"):
        decompose_model(
            DecompositionRequest(
                kind="declared",
                name="pipe",
                components=components,
                dependencies=[("missing", "solve")],
            )
        )


def test_cli_argument_introspection_never_runs_the_command():
    result = decompose_model(
        DecompositionRequest(
            kind="cli",
            name="command",
            argv=["/do/not/execute", "--input", "source.tif", "--iterations=10"],
        )
    )
    assert result.components[0].atomic
    assert result.cli_arguments == {"input": "source.tif", "iterations": "10"}
    assert result.executable is False
