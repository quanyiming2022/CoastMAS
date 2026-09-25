"""Explicit system and project administration, with no identity-based privilege guesses."""

from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request
from pydantic import Field, SecretStr, StrictBool
from sqlalchemy import delete, func, insert, select, update

from .batches import BatchIntake, source_grants
from .contracts import Contract
from .store import Problem, accounts, audit, audit_event, members, projects, sessions


class NewAccount(Contract):
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: SecretStr
    system_admin: StrictBool = False


class AccountState(Contract):
    active: StrictBool


class PasswordReset(Contract):
    password: SecretStr


class NewProject(Contract):
    name: str = Field(min_length=1, max_length=200)


class SetRole(Contract):
    role: Literal["viewer", "analyst", "curator", "manager"]


def require_admin(store, actor, connection):
    permitted = connection.scalar(
        select(accounts.c.system_admin).where(accounts.c.id == actor, accounts.c.active.is_(True))
    )
    if not permitted:
        raise Problem(403, "SYSTEM_ADMIN_REQUIRED", "仅系统管理员可管理全局账号与项目")


def router(store):
    routes = APIRouter()

    @routes.get("/api/accounts")
    def list_accounts(
        request: Request,
        search: str = "",
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 25,
    ):
        with store.engine.connect() as c:
            require_admin(store, request.state.actor["id"], c)
            condition = accounts.c.email.contains(search, autoescape=True)
            return {
                "items": [
                    dict(row)
                    for row in c.execute(
                        select(
                            accounts.c.id,
                            accounts.c.email,
                            accounts.c.active,
                            accounts.c.system_admin,
                        )
                        .where(condition)
                        .order_by(accounts.c.email)
                        .offset(offset)
                        .limit(limit)
                    ).mappings()
                ],
                "total": c.scalar(select(func.count()).select_from(accounts).where(condition)),
                "offset": offset,
                "limit": limit,
            }

    @routes.post("/api/accounts", status_code=201)
    def create_account(body: NewAccount, request: Request):
        actor = request.state.actor["id"]
        with store.engine.connect() as c:
            require_admin(store, actor, c)
        account = store.create_account(
            body.email, body.password.get_secret_value(), system_admin=body.system_admin
        )
        with store.engine.begin() as c:
            audit_event(c, actor, None, "create_account", account)
        return {
            "id": account,
            "email": body.email.strip().lower(),
            "active": True,
            "system_admin": body.system_admin,
        }

    @routes.put("/api/accounts/{account}/state")
    def account_state(account: str, body: AccountState, request: Request):
        actor = request.state.actor["id"]
        with store.engine.begin() as c:
            require_admin(store, actor, c)
            existing = (
                c.execute(select(accounts).where(accounts.c.id == account).with_for_update())
                .mappings()
                .first()
            )
            if existing is None:
                raise Problem(404, "ACCOUNT_UNAVAILABLE", "账号不存在")
            from .management_catalog import protect_account

            protect_account(c, actor, dict(existing), active=body.active)
            if not body.active:
                if actor == account:
                    raise Problem(409, "CURRENT_ACCOUNT", "不能在当前会话停用自己的账号")
                managed = list(
                    c.scalars(
                        select(members.c.project_id).where(
                            members.c.account_id == account, members.c.role == "manager"
                        )
                    )
                )
                for project in sorted(managed):
                    c.execute(
                        select(projects.c.id).where(projects.c.id == project).with_for_update()
                    ).one()
                    others = c.scalar(
                        select(func.count())
                        .select_from(members.join(accounts))
                        .where(
                            members.c.project_id == project,
                            members.c.role == "manager",
                            members.c.account_id != account,
                            accounts.c.active.is_(True),
                        )
                    )
                    if not others:
                        raise Problem(409, "LAST_MANAGER", "请先为相关项目指定另一位有效负责人")
                c.execute(delete(sessions).where(sessions.c.account_id == account))
            c.execute(update(accounts).where(accounts.c.id == account).values(active=body.active))
            audit_event(
                c, actor, None, "activate_account" if body.active else "deactivate_account", account
            )
        return {"id": account, "active": body.active}

    @routes.post("/api/accounts/{account}/password")
    def password(account: str, body: PasswordReset, request: Request):
        actor = request.state.actor["id"]
        value = body.password.get_secret_value()
        if len(value) < 12:
            raise Problem(422, "PASSWORD_LENGTH", "新密码至少12字符")
        with store.engine.begin() as c:
            require_admin(store, actor, c)
            changed = c.execute(
                update(accounts)
                .where(accounts.c.id == account)
                .values(password_hash=store.passwords.hash(value))
            ).rowcount
            if not changed:
                raise Problem(404, "ACCOUNT_UNAVAILABLE", "账号不存在")
            c.execute(delete(sessions).where(sessions.c.account_id == account))
            audit_event(c, actor, None, "reset_password", account)
        return {"reset": True, "sessions_revoked": True}

    @routes.post("/api/projects", status_code=201)
    def create_project(body: NewProject, request: Request):
        actor = request.state.actor["id"]
        with store.engine.connect() as c:
            require_admin(store, actor, c)
        project = store.create_project(actor, body.name)
        return {"id": project, "name": body.name, "role": "manager"}

    @routes.get("/api/projects/{project}/members")
    def list_members(project: str, request: Request):
        with store.engine.connect() as c:
            store.permission(c, request.state.actor["id"], project, manage=True)
            return [
                dict(row)
                for row in c.execute(
                    select(
                        members.c.account_id.label("id"),
                        accounts.c.email,
                        accounts.c.active,
                        members.c.role,
                    )
                    .join(accounts)
                    .where(members.c.project_id == project)
                    .order_by(accounts.c.email)
                ).mappings()
            ]

    @routes.get("/api/projects/{project}/member-candidates")
    def candidates(project: str, request: Request, search: str = ""):
        with store.engine.connect() as c:
            store.permission(c, request.state.actor["id"], project, manage=True)
            return [
                dict(row)
                for row in c.execute(
                    select(accounts.c.id, accounts.c.email)
                    .where(
                        accounts.c.active.is_(True),
                        accounts.c.email.contains(search, autoescape=True),
                    )
                    .order_by(accounts.c.email)
                    .limit(50)
                ).mappings()
            ]

    @routes.put("/api/projects/{project}/members/{account}")
    def membership(project: str, account: str, body: SetRole, request: Request):
        store.set_member(request.state.actor["id"], project, account, body.role)
        return {"id": account, "role": body.role}

    @routes.delete("/api/projects/{project}/members/{account}")
    def remove_member(project: str, account: str, request: Request):
        actor = request.state.actor["id"]
        with store.engine.begin() as c:
            c.execute(update(projects).where(projects.c.id == project).values(name=projects.c.name))
            store.permission(c, actor, project, manage=True)
            role = c.scalar(
                select(members.c.role).where(
                    members.c.project_id == project, members.c.account_id == account
                )
            )
            if role is None:
                raise Problem(404, "MEMBER_UNAVAILABLE", "该账号不是当前项目成员")
            if role == "manager" and not c.scalar(
                select(func.count())
                .select_from(members.join(accounts))
                .where(
                    members.c.project_id == project,
                    members.c.account_id != account,
                    members.c.role == "manager",
                    accounts.c.active.is_(True),
                )
            ):
                raise Problem(409, "LAST_MANAGER", "项目至少保留一位有效负责人")
            c.execute(
                delete(members).where(
                    members.c.project_id == project, members.c.account_id == account
                )
            )
            audit_event(c, actor, project, "remove_member", account)
        return {"removed": True, "account_retained": True}

    @routes.get("/api/projects/{project}/audit")
    def events(
        project: str,
        request: Request,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 25,
    ):
        with store.engine.connect() as c:
            store.permission(c, request.state.actor["id"], project, manage=True)
            condition = audit.c.project_id == project
            return {
                "items": [
                    dict(row)
                    for row in c.execute(
                        select(audit, accounts.c.email)
                        .outerjoin(accounts, audit.c.actor == accounts.c.id)
                        .where(condition)
                        .order_by(audit.c.created.desc(), audit.c.id)
                        .offset(offset)
                        .limit(limit)
                    ).mappings()
                ],
                "total": c.scalar(select(func.count()).select_from(audit).where(condition)),
                "offset": offset,
                "limit": limit,
            }

    @routes.post("/api/projects/{project}/local-sources/{source}/grant")
    def grant(project: str, source: str, request: Request):
        actor = request.state.actor["id"]
        with store.engine.begin() as c:
            require_admin(store, actor, c)
            store.permission(c, actor, project, manage=True)
            if source not in {item["id"] for item in BatchIntake(store).sources(actor, project)}:
                raise Problem(404, "SOURCE_UNAVAILABLE", "此来源连接尚未配置")
            c.execute(select(projects.c.id).where(projects.c.id == project).with_for_update()).one()
            if not c.scalar(
                select(source_grants.c.source_id).where(
                    source_grants.c.project_id == project, source_grants.c.source_id == source
                )
            ):
                c.execute(
                    insert(source_grants).values(project_id=project, source_id=source, actor=actor)
                )
                audit_event(c, actor, project, "grant_local_source", source)
        return {"granted": True}

    @routes.delete("/api/projects/{project}/local-sources/{source}/grant")
    def revoke(project: str, source: str, request: Request):
        actor = request.state.actor["id"]
        with store.engine.begin() as c:
            require_admin(store, actor, c)
            store.permission(c, actor, project, manage=True)
            c.execute(select(projects.c.id).where(projects.c.id == project).with_for_update()).one()
            count = c.execute(
                delete(source_grants).where(
                    source_grants.c.project_id == project, source_grants.c.source_id == source
                )
            ).rowcount
            if count:
                audit_event(c, actor, project, "revoke_local_source", source)
        return {"granted": False}

    return routes
