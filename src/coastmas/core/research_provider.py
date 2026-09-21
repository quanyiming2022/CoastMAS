"""Audited provider research trials, with frozen catalogs and no candidate execution."""

import hashlib
import ipaddress
from time import perf_counter
from typing import Literal
from urllib.parse import urlsplit

from pydantic import JsonValue, ValidationError
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from coastmas.core.errors import CoastMASError
from coastmas.core.execution import ExecutionRegistry
from coastmas.core.knowledge_graph import KnowledgeGraphService
from coastmas.core.llm import (
    LLMProvider,
    OpenAICompatibleProvider,
    PlanningPrompt,
    ProviderProposal,
)
from coastmas.core.model_documents import reject_embedded_credentials
from coastmas.core.planning import validate_provider_proposal
from coastmas.core.research import Experiment, TrialObservation
from coastmas.core.research_planning import ResearchCase, ResearchProviderIdentity, ResearchTrial
from coastmas.persistence.planning import create_trace, save_artifact
from coastmas.persistence.resources import fingerprint
from coastmas.persistence.schema import ProviderRequest

ProviderOrigin = Literal["LOCAL", "EXTERNAL", "MOCK"]


def research_prompt(case: ResearchCase, experiment: Experiment) -> PlanningPrompt:
    if experiment not in ("B", "C"):
        raise ValueError("provider research requires experiment B or C")
    if len(case.models) > 12 or len(case.assets) > 64:
        raise CoastMASError("CATALOG_LIMIT", "freeze a smaller complete research catalog")
    # Both arms see the same catalog and hard constraints. Only C receives actual
    # graph-derived candidate relationships. Neither receives files, URIs or code.
    models: list[dict[str, JsonValue]] = []
    for model in case.models:
        models.append(
            {
                "id": model.id,
                "version": model.version,
                "capabilities": list(model.capabilities),
                "inputs": [v.model_dump(mode="json") for v in model.inputs],
                "outputs": [v.model_dump(mode="json") for v in model.outputs],
                "parameters": [v.model_dump(mode="json") for v in model.parameters],
                "constraints": [v.model_dump(mode="json") for v in model.constraints],
                "supported_crs": list(model.supported_crs),
                "spatial_scale": model.spatial_scale.model_dump(mode="json"),
                "temporal_scale": model.temporal_scale.model_dump(mode="json"),
            }
        )
    data: list[dict[str, JsonValue]] = [
        {
            "id": asset.id,
            "version": asset.version,
            "checksum": asset.checksum,
            "type": asset.type,
            "format": asset.format,
            "crs": asset.crs,
            "vertical_datum": asset.vertical_datum,
            "time_start": asset.time_start.isoformat() if asset.time_start else None,
            "time_end": asset.time_end.isoformat() if asset.time_end else None,
            "time_resolution": asset.time_resolution,
            "variables": [v.model_dump(mode="json") for v in asset.variables],
            "quality": {
                k: v
                for k, v in asset.quality.items()
                if k in {"validated", "geometry", "spatial_resolution_m", "spatial_support_m"}
            },
        }
        for asset in case.assets
    ]
    summary: dict[str, JsonValue] = {
        "id": case.scene.id,
        "version": case.scene.version,
        "time_range": case.scene.time_range.model_dump(mode="json"),
        "required_outputs": list(case.scene.required_outputs),
        "entity_types": list(case.scene.entity_types),
        "scenario_conditions": case.scene.scenario_conditions,
        "constraints": [v.model_dump(mode="json") for v in case.scene.constraints],
        "quality_requirements": case.scene.quality_requirements,
        "selected_data": {k: v.model_dump(mode="json") for k, v in case.selected_data.items()},
        "data_policy": {
            k: v
            for k, v in case.scene.data_policy.items()
            if k in {"target_grid", "study_area_crs"}
        },
    }
    if experiment == "C":
        graph = KnowledgeGraphService.from_catalog(models=case.models).snapshot
        nodes = {node.id: node for node in graph.nodes}
        connections: list[JsonValue] = []
        for edge in graph.edges:
            if edge.type != "CAN_FOLLOW":
                continue
            source, target = nodes[edge.source].resource, nodes[edge.target].resource
            if source is not None and target is not None:
                connections.append(
                    {
                        "source": source.model_dump(mode="json"),
                        "target": target.model_dump(mode="json"),
                        "relation": edge.type,
                        "evidence": edge.evidence,
                        "requires_preflight": True,
                    }
                )
        summary["knowledge_graph"] = {
            "connections": connections,
            "interpretation": "Graph connections require scientific preflight.",
        }
    prompt = PlanningPrompt(
        goal=case.goal,
        scene_summary=summary,
        models=tuple(models),
        data=tuple(data),
        candidate_total=len(models),
    )
    reject_embedded_credentials(prompt.model_dump(mode="json"))
    return prompt


def evaluate_proposal_trial(
    case: ResearchCase,
    registry: ExecutionRegistry,
    proposal: ProviderProposal,
    *,
    experiment: Experiment,
    repetition: int,
    origin: ProviderOrigin,
    latency: float,
    requests: int,
    usage: dict[str, JsonValue] | None,
    trace_id: str,
) -> ResearchTrial:
    candidate = proposal.candidate_workflow is not None
    workflow = None
    diagnostics: tuple[str, ...] = ()
    if candidate:
        try:
            workflow = validate_provider_proposal(
                proposal, case.scene, case.models, case.assets, registry
            )
        except CoastMASError as exc:
            diagnostics = (exc.code,)
        except ValidationError:
            diagnostics = ("WORKFLOW_SCHEMA_INVALID",)
    elif proposal.missing_conditions:
        diagnostics = ("PLAN_INCOMPLETE",)
    return ResearchTrial(
        workflow=workflow,
        proposal=proposal,
        trace_id=trace_id,
        observation=TrialObservation(
            case_id=case.id,
            repetition=repetition,
            experiment=experiment,
            origin=origin,
            status="EVALUATED",
            latency_seconds=latency,
            candidate_present=candidate,
            workflow_valid=workflow is not None,
            constraint_violated=(workflow is None) if candidate else None,
            manual_corrections=None,
            provider_requests=requests,
            usage=usage,
            diagnostics=diagnostics,
        ),
    )


def evaluate_provider_case(
    case: ResearchCase,
    registry: ExecutionRegistry,
    *,
    experiment: Experiment,
    repetition: int,
    origin: ProviderOrigin,
    provider: LLMProvider,
    engine: Engine,
    user_id: str,
    project_id: str,
    key: str,
) -> ResearchTrial:
    started = perf_counter()
    prompt = research_prompt(case, experiment)
    with Session(engine) as session, session.begin():
        trace = create_trace(
            session,
            user_id,
            project_id,
            key=key,
            allow_external=True,
            max_provider_requests=1,
            inputs={
                "research_case": case.model_dump(mode="json"),
                "experiment": experiment,
                "repetition": repetition,
                "origin": origin,
                "methodology": "frozen-catalog-planning-v1",
                "allowed_prompt_fingerprints": [fingerprint(prompt.model_dump(mode="json"))],
            },
        )
        trace_id = trace.id
        if trace.artifact is not None:
            return ResearchTrial.model_validate(trace.artifact)
        previous_attempt = trace.reserved_requests > 0
    proposal = None
    diagnostic = "PROVIDER_PREVIOUS_ATTEMPT_NOT_REPLAYABLE"
    if not previous_attempt:
        try:
            response = provider.generate(engine, user_id, trace_id, prompt)
            proposal = response.proposal
        except CoastMASError as exc:
            diagnostic = exc.code
    # Dispatched calls come from the durable ledger, never the reservation count.
    with Session(engine) as session:
        records = list(
            session.scalars(
                select(ProviderRequest)
                .where(ProviderRequest.trace_id == trace_id)
                .order_by(ProviderRequest.ordinal)
            )
        )
        requests = sum(record.dispatched_at is not None for record in records)
        usage = records[0].usage if len(records) == 1 else None
    elapsed = perf_counter() - started
    if proposal is not None:
        trial = evaluate_proposal_trial(
            case,
            registry,
            proposal,
            experiment=experiment,
            repetition=repetition,
            origin=origin,
            latency=elapsed,
            requests=requests,
            usage=usage,
            trace_id=trace_id,
        )
    else:
        trial = ResearchTrial(
            workflow=None,
            trace_id=trace_id,
            observation=TrialObservation(
                case_id=case.id,
                repetition=repetition,
                experiment=experiment,
                origin=origin,
                status="FAILED",
                latency_seconds=elapsed,
                candidate_present=None,
                workflow_valid=None,
                constraint_violated=None,
                manual_corrections=None,
                provider_requests=requests,
                usage=usage,
                diagnostics=(diagnostic,),
            ),
        )
    with Session(engine) as session, session.begin():
        save_artifact(session, user_id, trace_id, trial.model_dump(mode="json"))
    return trial


def provider_identity(provider: OpenAICompatibleProvider) -> ResearchProviderIdentity:
    host = urlsplit(provider.settings.base_url).hostname
    local = host == "localhost"
    if host is not None:
        try:
            local = local or ipaddress.ip_address(host).is_loopback
        except ValueError:
            pass  # DNS names other than localhost remain classified as external endpoints.
    return ResearchProviderIdentity(
        origin="LOCAL" if local else "EXTERNAL",
        model=provider.settings.model,
        endpoint_sha256=hashlib.sha256(provider.settings.base_url.encode()).hexdigest(),
    )
