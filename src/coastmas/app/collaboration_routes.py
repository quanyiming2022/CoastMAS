"""Versioned stakeholder evidence, explicit publication and independent human review."""

from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import NAMESPACE_URL, uuid4, uuid5

from fastapi import APIRouter, Query
from pydantic import Field, JsonValue
from sqlalchemy import or_, select

from coastmas.app.dependencies import CurrentUser, DatabaseSession
from coastmas.app.run_routes import encode
from coastmas.core.collaboration import DiscussionText, ProposalComment, ProposalDraft, ProposalSpec
from coastmas.core.contracts import Contract, Name, Version, VersionReference
from coastmas.core.errors import CoastMASError
from coastmas.domain.collaboration import compare_constraints
from coastmas.persistence.collaboration import (
    participant_role,
    review_proposal,
    save_proposal,
    submit_proposal,
)
from coastmas.persistence.lifecycle import resource_history
from coastmas.persistence.resources import create_resource, read_resource, require_permission
from coastmas.persistence.schema import AuditLog, Membership, Resource, ResourceDependency, User

router = APIRouter(prefix="/api/v1", tags=["collaboration"])


class SaveProposalRequest(Contract):
    project_id: Name
    spec: ProposalDraft
    expected_version: Version | None = None


class ExpectedVersion(Contract):
    expected_version: Version


class ReviewRequest(ExpectedVersion):
    conclusion: Literal["REVIEWED", "RETURNED"]
    rationale: DiscussionText


class PublicationRequest(ExpectedVersion):
    published: bool


class CommentRequest(Contract):
    proposal_version: Version
    content: DiscussionText
    idempotency_key: Name


class CompareRequest(Contract):
    project_id: Name
    proposals: Annotated[tuple[VersionReference, ...], Field(min_length=1, max_length=20)]


def proposal_spec(
    identifier: str, session: DatabaseSession, user_id: str, version: int | None = None
) -> ProposalSpec:
    resource = session.get(Resource, identifier)
    if resource is None or resource.kind != "proposal":
        raise CoastMASError("NOT_FOUND", "proposal unavailable")
    return ProposalSpec.model_validate(
        read_resource(session, user_id=user_id, identifier=identifier, version=version).spec
    )


def is_public(session: DatabaseSession, user_id: str, project_id: str) -> bool:
    require_permission(session, user_id, project_id, "read", published=True)
    user = session.get(User, user_id)
    member = session.get(Membership, (project_id, user_id))
    return bool(user and not user.is_admin and member and member.role == "PUBLIC")


@router.get("/proposals")
def list_proposals(
    project_id: str,
    session: DatabaseSession,
    user_id: CurrentUser,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, JsonValue]]:
    public = is_public(session, user_id, project_id)
    query = select(Resource).where(
        Resource.project_id == project_id, Resource.kind == "proposal", Resource.archived.is_(False)
    )
    if public:
        query = query.where(or_(Resource.published.is_(True), Resource.owner_id == user_id))
    return [
        encode(read_resource(session, user_id=user_id, identifier=row.id))
        for row in session.scalars(
            query.order_by(Resource.name, Resource.id).limit(limit).offset(offset)
        )
    ]


@router.post("/proposals", status_code=201)
def save(
    body: SaveProposalRequest, session: DatabaseSession, user_id: CurrentUser
) -> dict[str, JsonValue]:
    revision = save_proposal(
        session,
        user_id=user_id,
        project_id=body.project_id,
        draft=body.spec,
        expected_version=body.expected_version,
    )
    session.commit()
    return encode(revision)


@router.post("/proposals/compare")
def compare(
    body: CompareRequest, session: DatabaseSession, user_id: CurrentUser
) -> dict[str, JsonValue]:
    is_public(session, user_id, body.project_id)
    specs = []
    for ref in body.proposals:
        spec = proposal_spec(ref.id, session, user_id, ref.version)
        resource = session.get(Resource, ref.id)
        if resource is None or resource.project_id != body.project_id:
            raise CoastMASError("AUTHORIZATION_ERROR", "proposals must belong to this project")
        specs.append(spec)
    return {
        "proposals": [item.model_dump(mode="json") for item in specs],
        "constraints": compare_constraints(tuple(specs)).model_dump(mode="json"),
    }


@router.get("/proposals/{identifier}")
def get(
    identifier: str,
    session: DatabaseSession,
    user_id: CurrentUser,
    version: int | None = Query(default=None, ge=1),
) -> dict[str, JsonValue]:
    proposal_spec(identifier, session, user_id, version)
    return encode(read_resource(session, user_id=user_id, identifier=identifier, version=version))


@router.get("/proposals/{identifier}/versions")
def versions(
    identifier: str, session: DatabaseSession, user_id: CurrentUser
) -> list[dict[str, JsonValue]]:
    proposal_spec(identifier, session, user_id)
    return [
        encode(revision)
        for revision in resource_history(session, user_id=user_id, identifier=identifier)
    ]


@router.post("/proposals/{identifier}/submit")
def submit(
    identifier: str, body: ExpectedVersion, session: DatabaseSession, user_id: CurrentUser
) -> dict[str, JsonValue]:
    revision = submit_proposal(
        session, user_id=user_id, identifier=identifier, expected_version=body.expected_version
    )
    session.commit()
    return encode(revision)


@router.post("/proposals/{identifier}/review")
def review(
    identifier: str, body: ReviewRequest, session: DatabaseSession, user_id: CurrentUser
) -> dict[str, JsonValue]:
    revision = review_proposal(
        session,
        user_id=user_id,
        identifier=identifier,
        expected_version=body.expected_version,
        conclusion=body.conclusion,
        rationale=body.rationale,
    )
    session.commit()
    return encode(revision)


def publish(
    identifier: str, kind: str, body: PublicationRequest, session: DatabaseSession, user_id: str
) -> dict[str, JsonValue]:
    resource = session.scalar(
        select(Resource)
        .where(Resource.id == identifier)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if resource is None or resource.kind != kind:
        raise CoastMASError("NOT_FOUND", "resource unavailable")
    require_permission(session, user_id, resource.project_id, "publish")
    if resource.current_version != body.expected_version:
        raise CoastMASError("VERSION_CONFLICT", "resource changed; reload before publishing")
    if resource.archived or not resource.enabled:
        raise CoastMASError("RESOURCE_ARCHIVED", "resource unavailable for publication")
    if (
        kind == "proposal"
        and body.published
        and proposal_spec(identifier, session, user_id).status != "REVIEWED"
    ):
        raise CoastMASError("VALIDATION_ERROR", "publication requires independent human review")
    if resource.published != body.published:
        session.add(
            AuditLog(
                id=str(uuid4()),
                who=user_id,
                action="PUBLICATION",
                resource=identifier,
                old_value={"published": resource.published},
                new_value={"published": body.published, "version": resource.current_version},
            )
        )
        resource.published = body.published
    session.commit()
    return {"id": identifier, "version": resource.current_version, "published": resource.published}


@router.put("/proposals/{identifier}/publication")
def publish_proposal(
    identifier: str, body: PublicationRequest, session: DatabaseSession, user_id: CurrentUser
) -> dict[str, JsonValue]:
    return publish(identifier, "proposal", body, session, user_id)


@router.put("/collaboration/scenes/{identifier}/publication")
def publish_scene(
    identifier: str, body: PublicationRequest, session: DatabaseSession, user_id: CurrentUser
) -> dict[str, JsonValue]:
    return publish(identifier, "scene", body, session, user_id)


@router.post("/proposals/{identifier}/comments", status_code=201)
def comment(
    identifier: str, body: CommentRequest, session: DatabaseSession, user_id: CurrentUser
) -> dict[str, JsonValue]:
    # Parent lock serializes retry keys and publication/revision races.
    resource = session.scalar(
        select(Resource)
        .where(Resource.id == identifier)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    proposal_spec(identifier, session, user_id, body.proposal_version)
    assert resource is not None
    role = participant_role(session, user_id, resource.project_id)
    comment_id = str(
        uuid5(NAMESPACE_URL, f"coastmas:comment:{identifier}:{user_id}:{body.idempotency_key}")
    )
    existing = session.get(Resource, comment_id)
    if existing is not None:
        revision = read_resource(session, user_id=user_id, identifier=comment_id)
        old = ProposalComment.model_validate(revision.spec)
        if (
            existing.kind != "proposal_comment"
            or old.content != body.content
            or old.proposal.version != body.proposal_version
        ):
            raise CoastMASError(
                "IDEMPOTENCY_CONFLICT", "comment key already used for different content"
            )
        return encode(revision)
    spec = ProposalComment(
        id=comment_id,
        name="Opinion",
        version=1,
        proposal=VersionReference(id=identifier, version=body.proposal_version),
        author_id=user_id,
        author_role=role,
        created_at=datetime.now(UTC),
        content=body.content,
    )
    revision = create_resource(
        session,
        user_id=user_id,
        project_id=resource.project_id,
        kind="proposal_comment",
        identifier=spec.id,
        name=spec.name,
        spec=spec.model_dump(mode="json"),
    )
    session.commit()
    return encode(revision)


@router.get("/proposals/{identifier}/comments")
def comments(
    identifier: str,
    session: DatabaseSession,
    user_id: CurrentUser,
    version: int = Query(ge=1),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, JsonValue]]:
    proposal_spec(identifier, session, user_id, version)
    query = (
        select(Resource)
        .join(ResourceDependency, Resource.id == ResourceDependency.source_id)
        .where(
            Resource.kind == "proposal_comment",
            ResourceDependency.target_id == identifier,
            ResourceDependency.target_version == version,
        )
        .order_by(Resource.id)
        .limit(limit)
        .offset(offset)
    )
    return [
        encode(read_resource(session, user_id=user_id, identifier=row.id))
        for row in session.scalars(query)
    ]


@router.get("/collaboration/scenes")
def scenes(
    project_id: str,
    session: DatabaseSession,
    user_id: CurrentUser,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, JsonValue]]:
    public = is_public(session, user_id, project_id)
    query = select(Resource).where(
        Resource.project_id == project_id,
        Resource.kind == "scene",
        Resource.archived.is_(False),
        Resource.enabled.is_(True),
    )
    if public:
        query = query.where(Resource.published.is_(True))
    return [
        encode(read_resource(session, user_id=user_id, identifier=row.id))
        for row in session.scalars(
            query.order_by(Resource.name, Resource.id).limit(limit).offset(offset)
        )
    ]


@router.get("/collaboration/access")
def access(project_id: str, session: DatabaseSession, user_id: CurrentUser) -> dict[str, JsonValue]:
    is_public(session, user_id, project_id)
    user = session.get(User, user_id)
    member = session.get(Membership, (project_id, user_id))
    return {
        "user_id": user_id,
        "role": "ADMIN" if user and user.is_admin else member.role if member else None,
    }
