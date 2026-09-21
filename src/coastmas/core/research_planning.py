"""Run research planning against frozen scientific inputs; never execute a candidate."""

from collections.abc import Callable
from threading import Event
from time import perf_counter
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from coastmas.core.contracts import (
    Contract,
    DataAssetSpec,
    ModelSpec,
    Name,
    SceneSpec,
    VersionReference,
    WorkflowSpec,
)
from coastmas.core.errors import CoastMASError
from coastmas.core.execution import ExecutionRegistry
from coastmas.core.llm import ProviderProposal
from coastmas.core.planning import build_template_plan, parse_template_goal
from coastmas.core.research import Experiment, TrialMetrics, TrialObservation, summarize_trials
from coastmas.core.validation import validate_workflow


class ResearchCase(Contract):
    id: Name
    goal: Annotated[str, Field(min_length=1, max_length=8000)]
    scene: SceneSpec
    models: Annotated[tuple[ModelSpec, ...], Field(min_length=1, max_length=64)]
    assets: Annotated[tuple[DataAssetSpec, ...], Field(max_length=128)]
    selected_data: dict[str, VersionReference] = Field(default_factory=dict, max_length=128)

    @model_validator(mode="after")
    def distinct_versions(self) -> Self:
        for collection in (self.models, self.assets):
            identities = {(item.id, item.version) for item in collection}
            if len(identities) != len(collection):
                raise ValueError("research catalog has duplicate resource versions")
        return self


class ResearchTrial(Contract):
    observation: TrialObservation
    workflow: WorkflowSpec | None
    proposal: ProviderProposal | None = None
    trace_id: Name | None = None

    @model_validator(mode="after")
    def candidate_agrees(self) -> Self:
        if self.observation.candidate_present is not None and (
            self.observation.candidate_present
            != (
                self.workflow is not None
                or (self.proposal is not None and self.proposal.candidate_workflow is not None)
            )
        ):
            raise ValueError("recorded candidate differs from saved workflow")
        return self


def evaluate_rule_case(
    case: ResearchCase, registry: ExecutionRegistry, *, repetition: int
) -> ResearchTrial:
    started = perf_counter()
    workflow = None
    diagnostics: tuple[str, ...] = ()
    valid = False
    violated = None
    try:
        goal = parse_template_goal(case.goal)
        plan = build_template_plan(
            goal, case.scene, case.models, case.assets, registry, selected_data=case.selected_data
        )
        workflow = plan.candidate_workflow
        diagnostics = tuple(condition.code for condition in plan.missing_conditions)
        if workflow is not None:
            report = validate_workflow(workflow, list(case.models), list(case.assets), case.scene)
            valid = report.valid
            violated = not report.valid
            diagnostics += tuple(issue.code for issue in report.issues)
    except CoastMASError as exc:
        diagnostics = (exc.code,)
    return ResearchTrial(
        workflow=workflow,
        observation=TrialObservation(
            case_id=case.id,
            repetition=repetition,
            experiment="A",
            origin="RULE",
            status="EVALUATED",
            latency_seconds=perf_counter() - started,
            candidate_present=workflow is not None,
            workflow_valid=valid,
            constraint_violated=violated,
            manual_corrections=None,
            provider_requests=0,
            usage=None,
            diagnostics=diagnostics,
        ),
    )


class ResearchProviderIdentity(Contract):
    origin: Literal["LOCAL", "EXTERNAL"]
    model: Name
    endpoint_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class ResearchManifest(Contract):
    kind: Literal["research_evaluation"] = "research_evaluation"
    schema_version: Literal[1] = 1
    request_checksum: Annotated[str | None, Field(pattern=r"^[a-f0-9]{64}$")] = None
    evaluation_id: Name = "standalone"
    provider: ResearchProviderIdentity | None = None
    cases: Annotated[tuple[ResearchCase, ...], Field(min_length=1, max_length=20)]
    experiments: Annotated[tuple[Experiment, ...], Field(min_length=1, max_length=3)]
    repetitions: Annotated[int, Field(strict=True, ge=1, le=5)] = 1

    @model_validator(mode="after")
    def bounded_unique_trials(self) -> Self:
        if len({case.id for case in self.cases}) != len(self.cases):
            raise ValueError("duplicate research case")
        if len(set(self.experiments)) != len(self.experiments):
            raise ValueError("duplicate research experiment")
        if len(self.cases) * len(self.experiments) * self.repetitions > 100:
            raise ValueError("research batch exceeds 100 trials")
        return self


class ResearchReport(Contract):
    status: Literal["COMPLETE", "PARTIAL", "BLOCKED"]
    trials: tuple[ResearchTrial, ...]
    metrics: tuple[TrialMetrics, ...]
    elapsed_seconds: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    methodology: Literal["frozen-catalog-planning-v1"] = "frozen-catalog-planning-v1"
    executes_candidates: Literal[False] = False


def evaluate_research(
    manifest: ResearchManifest,
    registry: ExecutionRegistry,
    *,
    cancel: Event | None = None,
    on_progress: Callable[[float], None] | None = None,
    provider_trial: Callable[[ResearchCase, Experiment, int], ResearchTrial] | None = None,
) -> ResearchReport:
    started = perf_counter()
    trials: list[ResearchTrial] = []
    total = len(manifest.cases) * len(manifest.experiments) * manifest.repetitions
    for case in manifest.cases:
        for repetition in range(1, manifest.repetitions + 1):
            for experiment in manifest.experiments:
                if cancel is not None and cancel.is_set():
                    raise CoastMASError("CANCELLED", "research evaluation cancelled")
                if experiment == "A":
                    trial = evaluate_rule_case(case, registry, repetition=repetition)
                elif provider_trial is not None:
                    trial = provider_trial(case, experiment, repetition)
                    if (
                        trial.observation.case_id,
                        trial.observation.experiment,
                        trial.observation.repetition,
                    ) != (case.id, experiment, repetition):
                        raise CoastMASError(
                            "RESEARCH_IDENTITY", "provider returned a different trial"
                        )
                else:
                    trial = ResearchTrial(
                        workflow=None,
                        observation=TrialObservation(
                            case_id=case.id,
                            repetition=repetition,
                            experiment=experiment,
                            origin="EXTERNAL",
                            status="BLOCKED",
                            latency_seconds=None,
                            candidate_present=None,
                            workflow_valid=None,
                            constraint_violated=None,
                            manual_corrections=None,
                            provider_requests=0,
                            usage=None,
                            diagnostics=("PROVIDER_NOT_CONFIGURED",),
                        ),
                    )
                trials.append(trial)
                if on_progress is not None:
                    on_progress(len(trials) / total)
    evaluated = sum(row.observation.status == "EVALUATED" for row in trials)
    return ResearchReport(
        status="COMPLETE" if evaluated == total else "PARTIAL" if evaluated else "BLOCKED",
        trials=tuple(trials),
        metrics=summarize_trials(tuple(row.observation for row in trials)),
        elapsed_seconds=perf_counter() - started,
    )
