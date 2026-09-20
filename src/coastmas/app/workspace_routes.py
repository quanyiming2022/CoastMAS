"""Project navigation, live dashboard, membership and administrator operations."""

from typing import Literal, Self, cast
from uuid import uuid4

from fastapi import APIRouter, Query, Request
from pydantic import Field, JsonValue, SecretStr, model_validator
from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from coastmas.app.dependencies import CurrentUser, DatabaseSession
from coastmas.core.contracts import Contract, ModelSpec, Name
from coastmas.core.errors import CoastMASError
from coastmas.core.execution import ExecutionRegistry
from coastmas.persistence.auth import hash_password
from coastmas.persistence.resources import require_permission
from coastmas.persistence.schema import (
    AuditLog,
    AuthSession,
    Job,
    Membership,
    Project,
    Resource,
    ResourceVersion,
    ResultBundle,
    User,
)

router = APIRouter(prefix="/api/v1", tags=["workspace"])
Role = Literal["ADMIN", "RESEARCHER", "MANAGER", "VIEWER"]


def _user(session: Session, identifier: str, *, admin: bool = False) -> User:
    user = session.scalar(
        select(User).where(User.id == identifier).execution_options(populate_existing=True)
    )
    if user is None or not user.active or (admin and not user.is_admin):
        raise CoastMASError(
            "AUTHORIZATION_ERROR", "administrator permission required" if admin else "access denied"
        )
    return user


def _audit(
    session: Session,
    who: str,
    action: str,
    resource: str,
    old: dict[str, JsonValue] | None,
    new: dict[str, JsonValue],
) -> None:
    session.add(
        AuditLog(
            id=str(uuid4()), who=who, action=action, resource=resource, old_value=old, new_value=new
        )
    )


@router.get("/projects")
def projects(session: DatabaseSession, user_id: CurrentUser) -> list[dict[str, JsonValue]]:
    account = _user(session, user_id)
    query = select(Project)
    if not account.is_admin:
        query = query.join(Membership).where(Membership.user_id == user_id)
    return [
        {"id": item.id, "name": item.name, "owner_id": item.owner_id}
        for item in session.scalars(query.order_by(Project.name, Project.id))
    ]


class NewProject(Contract):
    name: Name


@router.post("/projects", status_code=201)
def new_project(
    body: NewProject, session: DatabaseSession, user_id: CurrentUser
) -> dict[str, JsonValue]:
    _user(session, user_id)
    identifier = str(uuid4())
    session.add(Project(id=identifier, name=body.name, owner_id=user_id))
    session.flush()
    session.add(Membership(project_id=identifier, user_id=user_id, role="ADMIN"))
    _audit(session, user_id, "CREATE_PROJECT", identifier, None, {"name": body.name})
    session.commit()
    return {"id": identifier, "name": body.name, "owner_id": user_id}


@router.get("/dashboard")
def dashboard(
    project_id: str, request: Request, session: DatabaseSession, user_id: CurrentUser
) -> dict[str, JsonValue]:
    require_permission(session, user_id, project_id, "read")
    grouped: dict[str, int] = {
        kind: count
        for kind, count in session.execute(
            select(Resource.kind, func.count())
            .where(
                Resource.project_id == project_id,
                Resource.archived.is_(False),
            )
            .group_by(Resource.kind)
        ).all()
    }
    counts: dict[str, JsonValue] = {
        name: int(grouped.get(kind, 0))
        for name, kind in [
            ("models", "model"),
            ("data_assets", "data"),
            ("scenes", "scene"),
            ("workflows", "workflow"),
            ("entities", "entity"),
            ("assessments", "assessment"),
        ]
    }
    executable = 0
    registry = cast(ExecutionRegistry, request.app.state.registry)
    specs = session.scalars(
        select(ResourceVersion.spec)
        .join(
            Resource,
            (Resource.id == ResourceVersion.resource_id)
            & (Resource.current_version == ResourceVersion.version),
        )
        .where(
            Resource.project_id == project_id,
            Resource.kind == "model",
            Resource.enabled.is_(True),
            Resource.archived.is_(False),
        )
    )
    for payload in specs:
        model = ModelSpec.model_validate(payload)
        if model.validation_status != "VALIDATED" or model.execution_status != "EXECUTABLE":
            continue
        try:
            registry.resolve(model)
        except CoastMASError:
            continue
        executable += 1
    counts["executable_models"] = executable
    counts["results"] = int(
        session.scalar(
            select(func.count())
            .select_from(ResultBundle)
            .join(
                Job,
                Job.id == ResultBundle.job_id,
            )
            .where(Job.project_id == project_id)
        )
        or 0
    )
    states = session.execute(
        select(Job.status, func.count())
        .where(
            Job.project_id == project_id,
        )
        .group_by(Job.status)
    ).all()
    recent = session.scalars(
        select(Job).where(Job.project_id == project_id).order_by(Job.created_at.desc()).limit(10)
    )
    return {
        "counts": counts,
        "run_states": {state: count for state, count in states},
        "recent_runs": [
            {
                "id": job.id,
                "status": job.status,
                "progress": job.progress,
                "created_at": job.created_at.isoformat(),
            }
            for job in recent
        ],
        "provider_configured": request.app.state.llm_provider is not None,
    }


@router.get("/projects/{project_id}/members")
def members(
    project_id: str, session: DatabaseSession, user_id: CurrentUser
) -> list[dict[str, JsonValue]]:
    require_permission(session, user_id, project_id, "read")
    records = session.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.project_id == project_id)
        .order_by(User.email)
    )
    return [
        {"user_id": member.user_id, "email": user.email, "role": member.role, "active": user.active}
        for member, user in records
    ]


class MemberRole(Contract):
    role: Role


@router.put("/projects/{project_id}/members/{member_id}")
def set_member(
    project_id: str,
    member_id: str,
    body: MemberRole,
    session: DatabaseSession,
    user_id: CurrentUser,
) -> dict[str, JsonValue]:
    require_permission(session, user_id, project_id, "admin")
    project = session.scalar(select(Project).where(Project.id == project_id).with_for_update())
    require_permission(session, user_id, project_id, "admin")
    if project is None or session.get(User, member_id) is None:
        raise CoastMASError("NOT_FOUND", "project or user not found")
    member = session.get(Membership, (project_id, member_id), populate_existing=True)
    old: dict[str, JsonValue] | None = {"role": member.role} if member else None
    if member is not None and member.role == "ADMIN" and body.role != "ADMIN":
        count = session.scalar(
            select(func.count())
            .select_from(Membership)
            .where(
                Membership.project_id == project_id,
                Membership.role == "ADMIN",
            )
        )
        if count == 1:
            raise CoastMASError("LAST_ADMIN", "project must retain an administrator")
    if member is None:
        session.add(Membership(project_id=project_id, user_id=member_id, role=body.role))
    else:
        member.role = body.role
    _audit(
        session, user_id, "SET_MEMBER", project_id, old, {"user_id": member_id, "role": body.role}
    )
    session.commit()
    return {"project_id": project_id, "user_id": member_id, "role": body.role}


class NewUser(Contract):
    email: str = Field(min_length=3, max_length=320, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    password: SecretStr = Field(min_length=12, max_length=256)


class UserChange(Contract):
    active: bool | None = None
    is_admin: bool | None = None
    password: SecretStr | None = Field(default=None, min_length=12, max_length=256)

    @model_validator(mode="after")
    def nonempty(self) -> Self:
        if self.active is None and self.is_admin is None and self.password is None:
            raise ValueError("at least one user change is required")
        return self


def _public_user(user: User) -> dict[str, JsonValue]:
    return {"id": user.id, "email": user.email, "active": user.active, "is_admin": user.is_admin}


@router.get("/admin/users")
def users(
    session: DatabaseSession,
    user_id: CurrentUser,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, JsonValue]]:
    _user(session, user_id, admin=True)
    return [
        _public_user(user)
        for user in session.scalars(select(User).order_by(User.email).limit(limit).offset(offset))
    ]


@router.post("/admin/users", status_code=201)
def new_user(body: NewUser, session: DatabaseSession, user_id: CurrentUser) -> dict[str, JsonValue]:
    _user(session, user_id, admin=True)
    identifier = str(uuid4())
    inserted = session.scalar(
        insert(User)
        .values(
            id=identifier,
            email=body.email.strip().lower(),
            active=True,
            is_admin=False,
            password_hash=hash_password(body.password.get_secret_value()),
        )
        .on_conflict_do_nothing(index_elements=["email"])
        .returning(User.id)
    )
    if inserted is None:
        raise CoastMASError("VERSION_CONFLICT", "email is already registered")
    _audit(session, user_id, "CREATE_USER", identifier, None, {"email": body.email, "active": True})
    session.commit()
    return {
        "id": identifier,
        "email": body.email.strip().lower(),
        "active": True,
        "is_admin": False,
    }


@router.patch("/admin/users/{identifier}")
def change_user(
    identifier: str, body: UserChange, session: DatabaseSession, user_id: CurrentUser
) -> dict[str, JsonValue]:
    _user(session, user_id, admin=True)
    # Serialize administrator removal checks across different target user rows.
    session.execute(text("SELECT pg_advisory_xact_lock(hashtext('coastmas-admin-change'))"))
    _user(session, user_id, admin=True)
    user = session.scalar(
        select(User)
        .where(User.id == identifier)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if user is None:
        raise CoastMASError("NOT_FOUND", "user not found")
    old = _public_user(user)
    if user.is_admin and user.active and (body.active is False or body.is_admin is False):
        count = session.scalar(
            select(func.count())
            .select_from(User)
            .where(
                User.active.is_(True),
                User.is_admin.is_(True),
            )
        )
        if count == 1:
            raise CoastMASError("LAST_ADMIN", "system must retain an active administrator")
    if body.active is not None:
        user.active = body.active
    if body.is_admin is not None:
        user.is_admin = body.is_admin
    if body.password is not None:
        user.password_hash = hash_password(body.password.get_secret_value())
    if body.password is not None or body.active is False:
        session.execute(delete(AuthSession).where(AuthSession.user_id == identifier))
    current = _public_user(user)
    _audit(
        session,
        user_id,
        "UPDATE_USER",
        identifier,
        old,
        {**current, "password_changed": body.password is not None},
    )
    session.commit()
    return current


@router.get("/admin/audit")
def audit(
    session: DatabaseSession,
    user_id: CurrentUser,
    project_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, JsonValue]]:
    query = select(AuditLog)
    if project_id is None:
        _user(session, user_id, admin=True)
    else:
        require_permission(session, user_id, project_id, "admin")
        references = select(Resource.id).where(Resource.project_id == project_id)
        jobs = select(Job.id).where(Job.project_id == project_id)
        query = query.where(
            (AuditLog.resource == project_id)
            | AuditLog.resource.in_(references)
            | AuditLog.resource.in_(jobs)
        )
    records = session.scalars(
        query.order_by(AuditLog.when.desc(), AuditLog.id).limit(limit).offset(offset)
    )
    return [
        {
            "id": item.id,
            "who": item.who,
            "when": item.when.isoformat(),
            "action": item.action,
            "resource": item.resource,
            "old_value": item.old_value,
            "new_value": item.new_value,
        }
        for item in records
    ]
