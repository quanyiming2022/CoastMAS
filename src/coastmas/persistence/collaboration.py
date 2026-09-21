"""Human-owned proposal revisions; no automatic policy decision or score compensation."""

from datetime import UTC, datetime
from typing import Literal, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from coastmas.core.collaboration import HumanReview, ParticipantRole, ProposalDraft, ProposalSpec
from coastmas.core.errors import CoastMASError
from coastmas.persistence.resources import (
    Revision,
    create_resource,
    read_resource,
    require_permission,
    update_resource,
)
from coastmas.persistence.schema import Job, Membership, Resource, ResultBundle, User


def participant_role(session: Session, user_id: str, project_id: str) -> ParticipantRole:
    require_permission(session, user_id, project_id, "participate")
    user = session.get(User, user_id)
    assert user is not None
    if user.is_admin:
        return "ADMIN"
    member = session.get(Membership, (project_id, user_id))
    assert member is not None
    return cast(ParticipantRole, member.role)


def locked_proposal(
    session: Session, user_id: str, identifier: str, expected_version: int
) -> tuple[Resource, ProposalSpec]:
    resource = session.scalar(
        select(Resource)
        .where(Resource.id == identifier)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if resource is None or resource.kind != "proposal":
        raise CoastMASError("NOT_FOUND", "proposal unavailable")
    spec = ProposalSpec.model_validate(
        read_resource(session, user_id=user_id, identifier=identifier).spec
    )
    if resource.archived or not resource.enabled:
        raise CoastMASError("RESOURCE_ARCHIVED", "proposal unavailable for editing")
    if resource.current_version != expected_version:
        raise CoastMASError("VERSION_CONFLICT", "proposal changed; reload current revision")
    return resource, spec


def validate_evidence(
    session: Session, user_id: str, project_id: str, draft: ProposalDraft
) -> None:
    # A published scene permits participation, never access to unrelated private results.
    scene = session.get(Resource, draft.scene.id)
    if scene is None or scene.kind != "scene" or scene.project_id != project_id:
        raise CoastMASError("DEPENDENCY_CONFLICT", "scene is unavailable in this project")
    read_resource(session, user_id=user_id, identifier=draft.scene.id, version=draft.scene.version)
    if draft.evidence_results:
        require_permission(session, user_id, project_id, "read")
    for identifier in draft.evidence_results:
        result = session.get(ResultBundle, identifier)
        job = session.get(Job, result.job_id) if result else None
        pinned_scene = job.manifest.get("scene") if job else None
        if (
            job is None
            or job.project_id != project_id
            or job.status != "SUCCEEDED"
            or not isinstance(pinned_scene, dict)
            or pinned_scene.get("id") != draft.scene.id
            or pinned_scene.get("version") != draft.scene.version
        ):
            raise CoastMASError(
                "DEPENDENCY_CONFLICT",
                "evidence must be an actual successful result for the pinned scene",
            )


def save_proposal(
    session: Session,
    *,
    user_id: str,
    project_id: str,
    draft: ProposalDraft,
    expected_version: int | None = None,
) -> Revision:
    role = participant_role(session, user_id, project_id)
    author_id, author_role = user_id, role
    if expected_version is not None:
        resource, old = locked_proposal(session, user_id, draft.id, expected_version)
        if resource.owner_id != user_id or resource.project_id != project_id:
            raise CoastMASError("AUTHORIZATION_ERROR", "only the author can revise this proposal")
        author_id, author_role = old.author_id, old.author_role
    validate_evidence(session, user_id, project_id, draft)
    spec = ProposalSpec(**draft.model_dump(), author_id=author_id, author_role=author_role)
    if expected_version is None:
        return create_resource(
            session,
            user_id=user_id,
            project_id=project_id,
            kind="proposal",
            identifier=spec.id,
            name=spec.name,
            spec=spec.model_dump(mode="json"),
        )
    return update_resource(
        session,
        user_id=user_id,
        identifier=spec.id,
        expected_version=expected_version,
        spec=spec.model_dump(mode="json"),
    )


def submit_proposal(
    session: Session, *, user_id: str, identifier: str, expected_version: int
) -> Revision:
    resource, old = locked_proposal(session, user_id, identifier, expected_version)
    participant_role(session, user_id, resource.project_id)
    if resource.owner_id != user_id:
        raise CoastMASError("AUTHORIZATION_ERROR", "only the author can submit this proposal")
    if old.status not in {"DRAFT", "RETURNED"}:
        raise CoastMASError("VALIDATION_ERROR", "only draft or returned proposals can be submitted")
    validate_evidence(session, user_id, resource.project_id, old)
    spec = ProposalSpec.model_validate(
        {**old.model_dump(), "version": expected_version + 1, "status": "SUBMITTED", "review": None}
    )
    return update_resource(
        session,
        user_id=user_id,
        identifier=identifier,
        expected_version=expected_version,
        spec=spec.model_dump(mode="json"),
    )


def review_proposal(
    session: Session,
    *,
    user_id: str,
    identifier: str,
    expected_version: int,
    conclusion: Literal["REVIEWED", "RETURNED"],
    rationale: str,
) -> Revision:
    resource, old = locked_proposal(session, user_id, identifier, expected_version)
    require_permission(session, user_id, resource.project_id, "publish")
    if old.author_id == user_id:
        raise CoastMASError("AUTHORIZATION_ERROR", "authors cannot review their own proposal")
    if old.status != "SUBMITTED":
        raise CoastMASError("VALIDATION_ERROR", "human review requires a submitted proposal")
    review = HumanReview(
        reviewer_id=user_id,
        reviewed_at=datetime.now(UTC),
        conclusion=conclusion,
        rationale=rationale,
    )
    spec = ProposalSpec.model_validate(
        {
            **old.model_dump(),
            "version": expected_version + 1,
            "status": conclusion,
            "review": review,
        }
    )
    return update_resource(
        session,
        user_id=user_id,
        identifier=identifier,
        expected_version=expected_version,
        spec=spec.model_dump(mode="json"),
    )
