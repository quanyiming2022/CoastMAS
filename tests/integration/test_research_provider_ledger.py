"""Real local HTTP protocol and database; explicitly MOCK, never LLM science evidence."""

import json
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from coastmas.core.errors import CoastMASError
from coastmas.core.llm import OpenAICompatibleProvider, ProviderSettings
from coastmas.core.research_provider import evaluate_provider_case
from coastmas.persistence.schema import ProviderRequest
from tests.integration import test_llm_provider as protocol_fixtures
from tests.unit.test_research_provider import case_and_proposal

# Reuse the explicit MOCK HTTP fixture without relabeling it as a model experiment.
protocol_server = protocol_fixtures.server


def test_trial_replay_reuses_actual_ledger_without_second_network_call(
    engine, actors, protocol_server
):
    catalog, case, proposal = case_and_proposal()
    endpoint, requests, response = protocol_server
    response["choices"][0]["message"]["content"] = proposal.model_dump_json()
    provider = OpenAICompatibleProvider(
        ProviderSettings(
            base_url=endpoint,
            model="protocol-fixture",
            api_key="local-fixture-only",
            allow_private=True,
        )
    )
    arguments = dict(
        experiment="C",
        repetition=1,
        origin="MOCK",
        provider=provider,
        engine=engine,
        user_id=actors[0],
        project_id=actors[3],
        key=uuid4().hex,
    )
    first = evaluate_provider_case(case, catalog.registry, **arguments)
    second = evaluate_provider_case(case, catalog.registry, **arguments)
    assert second == first
    assert first.observation.workflow_valid is True
    assert first.observation.provider_requests == 1
    assert first.observation.usage["total_tokens"] == 132
    assert len(requests) == 1
    with Session(engine) as session:
        records = list(
            session.scalars(
                select(ProviderRequest).where(ProviderRequest.trace_id == first.trace_id)
            )
        )
    assert len(records) == 1 and records[0].dispatched_at is not None
    assert "knowledge_graph" in json.loads(requests[0]["messages"][1]["content"])["scene_summary"]
    arguments["user_id"] = actors[2]
    with pytest.raises(CoastMASError, match="permission"):
        evaluate_provider_case(case, catalog.registry, **arguments)
    assert len(requests) == 1


def test_reserved_but_undispatched_attempt_is_not_reported_as_real_call(
    engine, actors, protocol_server
):
    catalog, case, _ = case_and_proposal()
    endpoint, requests, _ = protocol_server
    provider = OpenAICompatibleProvider(
        ProviderSettings(
            base_url=endpoint,
            model="protocol-fixture",
            api_key="local-fixture-only",
            allow_private=False,
        )
    )
    arguments = dict(
        experiment="B",
        repetition=1,
        origin="MOCK",
        provider=provider,
        engine=engine,
        user_id=actors[0],
        project_id=actors[3],
        key=uuid4().hex,
    )
    trial = evaluate_provider_case(case, catalog.registry, **arguments)
    assert trial.observation.status == "FAILED"
    assert trial.observation.provider_requests == 0
    assert trial.observation.usage is None
    assert trial.observation.workflow_valid is None
    assert evaluate_provider_case(case, catalog.registry, **arguments) == trial
    assert not requests
