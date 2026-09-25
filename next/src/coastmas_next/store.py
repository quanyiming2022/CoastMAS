"""New persistence: project-scoped immutable revisions and optimistic writes."""

import hashlib
import secrets
import time
from uuid import uuid4

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    func,
    insert,
    select,
    text,
    update,
)
from sqlalchemy.exc import IntegrityError

from .config import Settings

metadata = MetaData()
accounts = Table(
    "accounts",
    metadata,
    Column("id", String, primary_key=True),
    Column("email", String, unique=True, nullable=False),
    Column("password_hash", String, nullable=False),
    Column("system_admin", Boolean, nullable=False),
    Column("active", Boolean, nullable=False, default=True),
)
projects = Table(
    "projects",
    metadata,
    Column("id", String, primary_key=True),
    Column("name", String, nullable=False),
)
members = Table(
    "members",
    metadata,
    Column("project_id", ForeignKey("projects.id"), primary_key=True),
    Column("account_id", ForeignKey("accounts.id"), primary_key=True),
    Column("role", String, nullable=False),
)
sessions = Table(
    "sessions",
    metadata,
    Column("digest", String, primary_key=True),
    Column("account_id", ForeignKey("accounts.id"), nullable=False),
    Column("csrf", String, nullable=False),
    Column("expires", Float, nullable=False),
)
tasks = Table(
    "tasks",
    metadata,
    Column("id", String, primary_key=True),
    Column("project_id", ForeignKey("projects.id"), nullable=False),
    Column("revision", Integer, nullable=False),
    Column("draft", JSON, nullable=False),
    Column("updated", Float, nullable=False),
)
revisions = Table(
    "task_revisions",
    metadata,
    Column("task_id", ForeignKey("tasks.id"), primary_key=True),
    Column("revision", Integer, primary_key=True),
    Column("draft", JSON, nullable=False),
    Column("actor", ForeignKey("accounts.id"), nullable=False),
    Column("created", Float, nullable=False),
)
audit = Table(
    "audit",
    metadata,
    Column("id", String, primary_key=True),
    Column("actor", String, nullable=False),
    Column("project_id", String),
    Column("action", String, nullable=False),
    Column("target", String, nullable=False),
    Column("created", Float, nullable=False),
)


class Problem(Exception):
    def __init__(self, status, code, message, details=None):
        self.status, self.code, self.message, self.details = status, code, message, details or {}


def identifier():
    return uuid4().hex


def audit_event(connection, actor, project, action, target):
    connection.execute(
        insert(audit).values(
            id=identifier(),
            actor=actor,
            project_id=project,
            action=action,
            target=target,
            created=time.time(),
        )
    )


class Store:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.engine = create_engine(
            settings.database_url,
            pool_pre_ping=True,
            connect_args={"check_same_thread": False}
            if settings.database_url.startswith("sqlite")
            else {},
        )
        self.passwords = PasswordHasher()

    def initialize(self):
        from .schema_upgrades import separate_asset_identity

        self.settings.storage_root.mkdir(parents=True, exist_ok=True)
        if self.engine.dialect.name == "postgresql":
            # PostgreSQL catalog checks and table creation must be one serialized transaction.
            # Otherwise independently started API/worker processes can race CREATE TYPE/TABLE.
            with self.engine.begin() as connection:
                connection.execute(text("SELECT pg_advisory_xact_lock(1864397181)"))
                metadata.create_all(connection)
                separate_asset_identity(connection, self.settings)
        elif self.engine.dialect.name == "sqlite":
            # Serialize schema inspection and creation across local API/worker processes.
            with self.engine.connect() as connection:
                foreign_keys = connection.exec_driver_sql("PRAGMA foreign_keys").scalar()
                connection.commit()
                connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
                connection.commit()
                connection.exec_driver_sql("BEGIN IMMEDIATE")
                try:
                    metadata.create_all(connection)
                    separate_asset_identity(connection, self.settings)
                    connection.commit()
                except BaseException:
                    connection.rollback()
                    raise
                finally:
                    connection.exec_driver_sql(f"PRAGMA foreign_keys={int(foreign_keys)}")
                    connection.commit()
        else:
            metadata.create_all(self.engine)

    def create_account(self, email, password, system_admin=False):
        if len(password) < 12:
            raise Problem(422, "PASSWORD_LENGTH", "密码至少12字符")
        account = identifier()
        try:
            with self.engine.begin() as c:
                c.execute(
                    insert(accounts).values(
                        id=account,
                        email=email.strip().lower(),
                        password_hash=self.passwords.hash(password),
                        system_admin=system_admin,
                        active=True,
                    )
                )
        except IntegrityError as exc:
            raise Problem(409, "ACCOUNT_EXISTS", "账号已存在") from exc
        return account

    def create_project(self, actor, name):
        project = identifier()
        with self.engine.begin() as c:
            c.execute(insert(projects).values(id=project, name=name))
            c.execute(insert(members).values(project_id=project, account_id=actor, role="manager"))
            audit_event(c, actor, project, "create_project", project)
        return project

    def permission(self, c, actor, project, write=False, manage=False):
        role = c.scalar(
            select(members.c.role)
            .join(accounts)
            .where(
                members.c.project_id == project,
                members.c.account_id == actor,
                accounts.c.active.is_(True),
            )
        )
        if role is None:
            raise Problem(404, "PROJECT_UNAVAILABLE", "项目不可用")
        if (write and role == "viewer") or (manage and role != "manager"):
            raise Problem(403, "PERMISSION_DENIED", "当前角色无权执行此操作")
        return role

    def set_member(self, actor, project, member, role):
        if role not in {"viewer", "analyst", "curator", "manager"}:
            raise Problem(422, "ROLE_INVALID", "未知角色")
        with self.engine.begin() as c:
            c.execute(
                select(projects.c.id).where(projects.c.id == project).with_for_update()
            ).first()
            self.permission(c, actor, project, manage=True)
            if not c.scalar(select(accounts.c.active).where(accounts.c.id == member)):
                raise Problem(404, "ACCOUNT_UNAVAILABLE", "请先选择有效账号")
            if role != "manager":
                existing_role = c.scalar(
                    select(members.c.role).where(
                        members.c.project_id == project, members.c.account_id == member
                    )
                )
                if existing_role == "manager" and not c.scalar(
                    select(func.count())
                    .select_from(members.join(accounts))
                    .where(
                        members.c.project_id == project,
                        members.c.role == "manager",
                        members.c.account_id != member,
                        accounts.c.active.is_(True),
                    )
                ):
                    raise Problem(409, "LAST_MANAGER", "项目至少保留一位有效负责人")
            exists = c.scalar(
                select(members.c.role).where(
                    members.c.project_id == project, members.c.account_id == member
                )
            )
            if exists:
                c.execute(
                    update(members)
                    .where(members.c.project_id == project, members.c.account_id == member)
                    .values(role=role)
                )
            else:
                c.execute(insert(members).values(project_id=project, account_id=member, role=role))
            audit_event(c, actor, project, "set_member", member)

    def sign_in(self, email, password):
        with self.engine.begin() as c:
            account = (
                c.execute(
                    select(accounts).where(
                        accounts.c.email == email.strip().lower(), accounts.c.active.is_(True)
                    )
                )
                .mappings()
                .first()
            )
            valid = False
            if account:
                try:
                    valid = self.passwords.verify(account["password_hash"], password)
                except VerificationError:
                    pass
            if not valid:
                raise Problem(401, "LOGIN_FAILED", "邮箱或密码不正确")
            token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            c.execute(
                insert(sessions).values(
                    digest=hashlib.sha256(token.encode()).hexdigest(),
                    account_id=account["id"],
                    csrf=csrf,
                    expires=time.time() + 43200,
                )
            )
            return token, csrf

    def authenticate(self, token):
        if not token:
            raise Problem(401, "LOGIN_REQUIRED", "请登录")
        with self.engine.connect() as c:
            row = (
                c.execute(
                    select(
                        accounts.c.id, accounts.c.email, accounts.c.system_admin, sessions.c.csrf
                    )
                    .join(sessions)
                    .where(
                        sessions.c.digest == hashlib.sha256(token.encode()).hexdigest(),
                        sessions.c.expires > time.time(),
                        accounts.c.active.is_(True),
                    )
                )
                .mappings()
                .first()
            )
            if not row:
                raise Problem(401, "LOGIN_REQUIRED", "登录已失效")
            return dict(row)

    def project_list(self, actor):
        with self.engine.connect() as c:
            return [
                dict(r)
                for r in c.execute(
                    select(projects.c.id, projects.c.name, members.c.role)
                    .join(members)
                    .where(members.c.account_id == actor)
                ).mappings()
            ]

    def new_task(self, actor, project, draft):
        task = identifier()
        with self.engine.begin() as c:
            self.permission(c, actor, project, write=True)
            from .management_catalog import require_available
            require_available(c, "projects", project)
            c.execute(
                insert(tasks).values(
                    id=task, project_id=project, revision=1, draft=draft, updated=time.time()
                )
            )
            c.execute(
                insert(revisions).values(
                    task_id=task, revision=1, draft=draft, actor=actor, created=time.time()
                )
            )
            audit_event(c, actor, project, "create_task", task)
        return self.task(actor, task)

    def task(self, actor, task, write=False, connection=None):
        if connection is None:
            with self.engine.connect() as c:
                return self.task(actor, task, write, c)
        row = connection.execute(select(tasks).where(tasks.c.id == task)).mappings().first()
        if not row:
            raise Problem(404, "TASK_UNAVAILABLE", "任务不可用")
        self.permission(connection, actor, row["project_id"], write=write)
        return dict(row)

    def save_task(self, actor, task, revision, draft, connection=None):
        if connection is None:
            with self.engine.begin() as c:
                return self.save_task(actor, task, revision, draft, c)
        c = connection
        current = self.task(actor, task, write=True, connection=c)
        from .management_catalog import require_available
        require_available(c, "projects", current["project_id"])
        require_available(c, "tasks", task)
        count = c.execute(
            update(tasks)
            .where(tasks.c.id == task, tasks.c.revision == revision)
            .values(revision=revision + 1, draft=draft, updated=time.time())
        ).rowcount
        if count != 1:
            raise Problem(
                409,
                "DRAFT_CONFLICT",
                "已有更新版本，请比较后保存；当前编辑内容应保留",
                {"current_revision": current["revision"]},
            )
        c.execute(
            insert(revisions).values(
                task_id=task,
                revision=revision + 1,
                draft=draft,
                actor=actor,
                created=time.time(),
            )
        )
        audit_event(c, actor, current["project_id"], "save_draft", task)
        return self.task(actor, task, connection=c)
