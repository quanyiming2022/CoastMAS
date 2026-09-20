import pytest
from pydantic import ValidationError

from coastmas.core.llm import ProviderPlanningArtifact


def test_provider_artifact_preserves_unknown_usage_and_requires_review():
    payload = {
        "origin": "provider_candidate",
        "proposal": {
            "management_goal": "test goal",
            "task_graph": [],
            "required_data": [],
            "required_capabilities": [],
            "candidate_workflow": None,
            "missing_conditions": ["missing input"],
            "rationale": ["test only"],
        },
        "candidate_workflow": None,
        "missing_conditions": ["missing input"],
        "request_id": "request-1",
        "usage": None,
        "interpretation_requires_review": True,
    }
    artifact = ProviderPlanningArtifact.model_validate(payload)
    assert artifact.usage is None
    assert artifact.model_dump(mode="json") == payload
    with pytest.raises(ValidationError):
        ProviderPlanningArtifact.model_validate(
            {**payload, "interpretation_requires_review": False}
        )
