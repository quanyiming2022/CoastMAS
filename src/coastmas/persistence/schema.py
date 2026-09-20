"""One relational source of truth for project access and contract versions."""

from datetime import datetime

from pydantic import JsonValue
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Metadata used by queries; schema changes are applied only by Alembic."""


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(256))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"))


class Membership(Base):
    __tablename__ = "project_memberships"
    __table_args__ = (
        CheckConstraint("role IN ('ADMIN','RESEARCHER','MANAGER','VIEWER','PUBLIC')"),
    )
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String(16))


class Resource(Base):
    __tablename__ = "resources"
    __table_args__ = (
        ForeignKeyConstraint(
            ["id", "current_version"],
            ["resource_versions.resource_id", "resource_versions.version"],
            name="resource_current_version_fk",
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
        ),
    )
    id: Mapped[str] = mapped_column(String(256), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(256))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    current_version: Mapped[int] = mapped_column(Integer)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    published: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class ResourceVersion(Base):
    __tablename__ = "resource_versions"
    resource_id: Mapped[str] = mapped_column(ForeignKey("resources.id"), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    spec: Mapped[dict[str, JsonValue]] = mapped_column(JSONB)
    checksum: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ResourceDependency(Base):
    __tablename__ = "resource_dependencies"
    __table_args__ = (
        ForeignKeyConstraint(
            ["source_id", "source_version"],
            ["resource_versions.resource_id", "resource_versions.version"],
        ),
        ForeignKeyConstraint(
            ["target_id", "target_version"],
            ["resource_versions.resource_id", "resource_versions.version"],
        ),
    )
    source_id: Mapped[str] = mapped_column(String(256), primary_key=True)
    source_version: Mapped[int] = mapped_column(Integer, primary_key=True)
    target_id: Mapped[str] = mapped_column(String(256), primary_key=True)
    target_version: Mapped[int] = mapped_column(Integer, primary_key=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    who: Mapped[str] = mapped_column(ForeignKey("users.id"))
    when: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    action: Mapped[str] = mapped_column(String(32))
    resource: Mapped[str] = mapped_column(String(256))
    old_value: Mapped[dict[str, JsonValue] | None] = mapped_column(JSONB, nullable=True)
    new_value: Mapped[dict[str, JsonValue] | None] = mapped_column(JSONB, nullable=True)


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (UniqueConstraint("project_id", "submitted_by", "idempotency_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    submitted_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    idempotency_key: Mapped[str] = mapped_column(String(256))
    fingerprint: Mapped[str] = mapped_column(String(64))
    manifest: Mapped[dict[str, JsonValue]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(16), default="QUEUED", server_default="QUEUED")
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    worker_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempt: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    progress: Mapped[float] = mapped_column(Float, default=0, server_default="0")
    error: Mapped[dict[str, JsonValue] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ResultBundle(Base):
    __tablename__ = "result_bundles"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), unique=True)
    manifest: Mapped[dict[str, JsonValue]] = mapped_column(JSONB)
    checksum: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
