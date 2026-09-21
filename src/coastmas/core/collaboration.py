"""Versioned stakeholder proposals; review records document people, not automated policy."""

import math
from typing import Annotated, Literal, Self

import pint
from pydantic import AwareDatetime, Field, model_validator

from coastmas.core.contracts import UNITS, Contract, Name, Version, VersionReference

FiniteNumber = Annotated[float, Field(strict=True, allow_inf_nan=False)]
DiscussionText = Annotated[str, Field(min_length=1, max_length=10000, pattern=r".*\S.*")]
ParticipantRole = Literal["ADMIN", "RESEARCHER", "MANAGER", "PUBLIC"]


class ObjectiveWeight(Contract):
    objective_id: Name
    name: Name
    weight: Annotated[FiniteNumber, Field(ge=0)]


class QuantitativeConstraint(Contract):
    constraint_id: Name
    metric: Name
    unit: Name
    minimum: FiniteNumber | None = None
    maximum: FiniteNumber | None = None

    @model_validator(mode="after")
    def explicit_interval(self) -> Self:
        if self.minimum is None and self.maximum is None:
            raise ValueError("a quantitative constraint needs at least one boundary")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("constraint minimum exceeds maximum")
        try:
            UNITS.Unit(self.unit)
        except (pint.UndefinedUnitError, ValueError, TypeError) as exc:
            raise ValueError("constraint unit is unknown") from exc
        return self


class ProposalDraft(Contract):
    id: Name
    name: Name
    version: Version
    scene: VersionReference
    rationale: DiscussionText
    objectives: Annotated[tuple[ObjectiveWeight, ...], Field(min_length=1, max_length=32)]
    constraints: Annotated[tuple[QuantitativeConstraint, ...], Field(max_length=64)]
    evidence_results: Annotated[tuple[Name, ...], Field(max_length=32)] = ()

    @model_validator(mode="after")
    def unambiguous(self) -> Self:
        objective_ids = [item.objective_id for item in self.objectives]
        constraint_ids = [item.constraint_id for item in self.constraints]
        if len(set(objective_ids)) != len(objective_ids) or len(set(constraint_ids)) != len(
            constraint_ids
        ):
            raise ValueError("objective and constraint identifiers must each be unique")
        total = sum(item.weight for item in self.objectives)
        if not math.isfinite(total) or total <= 0:
            raise ValueError("objective weights require a finite positive total")
        if len(set(self.evidence_results)) != len(self.evidence_results):
            raise ValueError("result references must be unique")
        return self


class HumanReview(Contract):
    reviewer_id: Name
    reviewed_at: AwareDatetime
    conclusion: Literal["REVIEWED", "RETURNED"]
    rationale: DiscussionText


class ProposalSpec(ProposalDraft):
    author_id: Name
    author_role: ParticipantRole
    status: Literal["DRAFT", "SUBMITTED", "REVIEWED", "RETURNED"] = "DRAFT"
    review: HumanReview | None = None

    @model_validator(mode="after")
    def reviewed_state(self) -> Self:
        if self.status in {"REVIEWED", "RETURNED"}:
            if self.review is None or self.review.conclusion != self.status:
                raise ValueError("reviewed state requires a matching human review record")
        elif self.review is not None:
            raise ValueError("draft and submitted proposals cannot claim review completion")
        return self


class ProposalComment(Contract):
    id: Name
    name: Name
    version: Version
    proposal: VersionReference
    author_id: Name
    author_role: ParticipantRole
    created_at: AwareDatetime
    content: DiscussionText


class ConstraintSource(Contract):
    proposal_id: Name
    version: Version
    constraint_id: Name


class ConstraintIntersection(Contract):
    metric: Name
    unit: Name
    minimum: FiniteNumber | None
    maximum: FiniteNumber | None
    sources: tuple[ConstraintSource, ...]


class ConstraintConflict(ConstraintIntersection):
    code: Literal["EMPTY_INTERVAL", "UNIT_MISMATCH", "UNIT_CONVERSION_FAILED"]


class ConstraintComparison(Contract):
    policy_decision: Literal[False] = False
    intersections: tuple[ConstraintIntersection, ...]
    conflicts: tuple[ConstraintConflict, ...]
