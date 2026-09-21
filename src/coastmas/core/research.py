"""Research observations and explicit denominators; missing evidence is never a zero."""

from collections import defaultdict
from typing import Annotated, Literal, Self

from pydantic import Field, JsonValue, StrictBool, model_validator

from coastmas.core.contracts import Contract, Name

Count = Annotated[int, Field(strict=True, ge=0)]
Seconds = Annotated[float, Field(ge=0, allow_inf_nan=False)]
Experiment = Literal["A", "B", "C"]
Origin = Literal["RULE", "EXTERNAL", "MOCK", "REPLAY"]


class TrialObservation(Contract):
    case_id: Name
    repetition: Annotated[int, Field(strict=True, ge=1)]
    experiment: Experiment
    origin: Origin
    status: Literal["EVALUATED", "BLOCKED", "FAILED"]
    latency_seconds: Seconds | None
    candidate_present: StrictBool | None
    workflow_valid: StrictBool | None
    constraint_violated: StrictBool | None
    manual_corrections: Count | None
    provider_requests: Count
    usage: dict[str, JsonValue] | None
    diagnostics: tuple[str, ...]

    @model_validator(mode="after")
    def consistent_evidence(self) -> Self:
        if (self.experiment == "A") != (self.origin == "RULE"):
            raise ValueError("rule-only experiment and RULE origin must agree")
        if self.origin in {"RULE", "REPLAY"} and self.provider_requests:
            raise ValueError("rule and replay trials cannot report provider requests")
        if self.status == "EVALUATED":
            if self.candidate_present is None or self.workflow_valid is None:
                raise ValueError("evaluated trials require candidate and validity observations")
            if self.latency_seconds is None:
                raise ValueError("evaluated trials require measured latency")
        elif any(
            value is not None
            for value in (self.candidate_present, self.workflow_valid, self.constraint_violated)
        ):
            raise ValueError("unevaluated trials cannot claim workflow or constraint outcomes")
        if self.workflow_valid and (
            not self.candidate_present or self.constraint_violated is not False
        ):
            raise ValueError("valid workflow requires a candidate and no constraint violation")
        if self.constraint_violated is not None and not self.candidate_present:
            raise ValueError("constraint audit requires an actual candidate")
        return self


class TrialMetrics(Contract):
    experiment: Experiment
    origin: Origin
    total: Count
    evaluated: Count
    blocked: Count
    failed: Count
    evaluation_completion_rate: float
    workflow_validity_rate: float | None
    constraint_observations: Count
    constraint_violation_rate: float | None
    manual_observations: Count
    manual_correction_count: Count | None
    latency_observations: Count
    mean_latency_seconds: Seconds | None
    provider_requests: Count
    usage_observations: Count
    total_tokens: Count | None


def summarize_trials(trials: tuple[TrialObservation, ...]) -> tuple[TrialMetrics, ...]:
    grouped: dict[tuple[Experiment, Origin], list[TrialObservation]] = defaultdict(list)
    identities = set()
    for trial in trials:
        identity = (trial.case_id, trial.repetition, trial.experiment, trial.origin)
        if identity in identities:
            raise ValueError("duplicate research trial")
        identities.add(identity)
        grouped[(trial.experiment, trial.origin)].append(trial)
    summaries = []
    for (experiment, origin), rows in sorted(grouped.items()):
        evaluated = [row for row in rows if row.status == "EVALUATED"]
        constraints = [
            row.constraint_violated for row in rows if row.constraint_violated is not None
        ]
        manual = [row.manual_corrections for row in rows if row.manual_corrections is not None]
        latencies = [row.latency_seconds for row in rows if row.latency_seconds is not None]
        tokens = []
        for row in rows:
            value = row.usage.get("total_tokens") if row.usage is not None else None
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                tokens.append(value)
        summaries.append(
            TrialMetrics(
                experiment=experiment,
                origin=origin,
                total=len(rows),
                evaluated=len(evaluated),
                blocked=sum(row.status == "BLOCKED" for row in rows),
                failed=sum(row.status == "FAILED" for row in rows),
                evaluation_completion_rate=len(evaluated) / len(rows),
                workflow_validity_rate=sum(row.workflow_valid is True for row in evaluated)
                / len(evaluated)
                if evaluated
                else None,
                constraint_observations=len(constraints),
                constraint_violation_rate=sum(constraints) / len(constraints)
                if constraints
                else None,
                manual_observations=len(manual),
                manual_correction_count=sum(manual) if len(manual) == len(rows) else None,
                latency_observations=len(latencies),
                mean_latency_seconds=sum(latencies) / len(latencies) if latencies else None,
                provider_requests=sum(row.provider_requests for row in rows),
                usage_observations=len(tokens),
                total_tokens=sum(tokens) if len(tokens) == len(rows) else None,
            )
        )
    return tuple(summaries)
