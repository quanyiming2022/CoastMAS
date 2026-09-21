"""Hard-constraint intersection. Objective preferences never compensate infeasibility."""

from coastmas.core.binding import convert_units
from coastmas.core.collaboration import (
    ConstraintComparison,
    ConstraintConflict,
    ConstraintIntersection,
    ConstraintSource,
    ProposalDraft,
    QuantitativeConstraint,
)
from coastmas.core.contracts import UNITS
from coastmas.core.errors import ConstraintError


def compare_constraints(proposals: tuple[ProposalDraft, ...]) -> ConstraintComparison:
    if not 1 <= len(proposals) <= 20:
        raise ConstraintError("comparison requires one to twenty explicit proposal versions")
    identities = [(item.id, item.version) for item in proposals]
    if len(set(identities)) != len(identities):
        raise ConstraintError("comparison proposal versions must be unique")
    groups: dict[str, list[tuple[QuantitativeConstraint, ConstraintSource]]] = {}
    for proposal in proposals:
        for constraint in proposal.constraints:
            groups.setdefault(constraint.metric, []).append(
                (
                    constraint,
                    ConstraintSource(
                        proposal_id=proposal.id,
                        version=proposal.version,
                        constraint_id=constraint.constraint_id,
                    ),
                )
            )
    intersections = []
    conflicts = []
    for metric, entries in sorted(groups.items()):
        unit = entries[0][0].unit
        sources = tuple(source for _, source in entries)
        if any(
            not UNITS.Unit(constraint.unit).is_compatible_with(unit) for constraint, _ in entries
        ):
            conflicts.append(
                ConstraintConflict(
                    metric=metric,
                    unit=unit,
                    minimum=None,
                    maximum=None,
                    sources=sources,
                    code="UNIT_MISMATCH",
                )
            )
            continue
        lower = []
        upper = []
        try:
            for constraint, _ in entries:
                if constraint.minimum is not None:
                    lower.append(
                        float(convert_units([constraint.minimum], constraint.unit, unit)[0])
                    )
                if constraint.maximum is not None:
                    upper.append(
                        float(convert_units([constraint.maximum], constraint.unit, unit)[0])
                    )
        except ConstraintError:
            conflicts.append(
                ConstraintConflict(
                    metric=metric,
                    unit=unit,
                    minimum=None,
                    maximum=None,
                    sources=sources,
                    code="UNIT_CONVERSION_FAILED",
                )
            )
            continue
        interval = ConstraintIntersection(
            metric=metric,
            unit=unit,
            minimum=max(lower) if lower else None,
            maximum=min(upper) if upper else None,
            sources=sources,
        )
        intersections.append(interval)
        if (
            interval.minimum is not None
            and interval.maximum is not None
            and interval.minimum > interval.maximum
        ):
            conflicts.append(ConstraintConflict(**interval.model_dump(), code="EMPTY_INTERVAL"))
    return ConstraintComparison(intersections=tuple(intersections), conflicts=tuple(conflicts))
