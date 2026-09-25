"""Project discussion and technical review bound to immutable comparison runs."""

import time
from typing import Literal

from fastapi import APIRouter, Query, Request
from pydantic import Field
from sqlalchemy import (
    JSON,
    Column,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    UniqueConstraint,
    func,
    insert,
    select,
    update,
)

from .contracts import Contract
from .execution import Execution, jobs
from .store import Problem, audit_event, identifier, metadata

opinion_drafts = Table(
    "opinion_drafts",
    metadata,
    Column("job_id", ForeignKey("jobs.id"), primary_key=True),
    Column("actor", ForeignKey("accounts.id"), primary_key=True),
    Column("revision", Integer, nullable=False),
    Column("text", String, nullable=False),
    Column("perspective", String),
)
comments = Table(
    "scenario_comments",
    metadata,
    Column("id", String, primary_key=True),
    Column("job_id", ForeignKey("jobs.id"), nullable=False),
    Column("actor", ForeignKey("accounts.id"), nullable=False),
    Column("author", String, nullable=False),
    Column("role", String, nullable=False),
    Column("origin_revision", Integer, nullable=False),
    Column("idempotency_key", String, nullable=False),
    Column("text", String, nullable=False),
    Column("perspective", String, nullable=False),
    Column("created", Float, nullable=False),
    UniqueConstraint("job_id", "actor", "idempotency_key"),
)
reviews = Table(
    "scenario_reviews",
    metadata,
    Column("id", String, primary_key=True),
    Column("job_id", ForeignKey("jobs.id"), nullable=False),
    Column("actor", ForeignKey("accounts.id"), nullable=False),
    Column("author", String, nullable=False),
    Column("revision", Integer, nullable=False),
    Column("status", String, nullable=False),
    Column("note", String, nullable=False),
    Column("idempotency_key", String, nullable=False),
    Column("request", JSON, nullable=False),
    Column("created", Float, nullable=False),
    UniqueConstraint("job_id", "revision"),
    UniqueConstraint("job_id", "actor", "idempotency_key"),
)


class SaveOpinion(Contract):
    expected_revision: int = Field(ge=0)
    text: str = Field(max_length=10000)
    perspective: Literal["research", "management", "public"] | None = None


class PublishOpinion(Contract):
    expected_revision: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)


class ReviewRequest(Contract):
    expected_revision: int = Field(ge=0)
    status: Literal["reviewed", "changes_requested"]
    note: str = Field(min_length=1, max_length=10000)
    idempotency_key: str = Field(min_length=1, max_length=128)


def router(store):
    routes = APIRouter()

    def require(c, actor, job_id, *, write=False, manage=False, lock=False):
        job = Execution(store).read_job(actor, job_id, write=write, connection=c)
        role = store.permission(c, actor, job["project_id"], write=write, manage=manage)
        if job["status"] != "succeeded" or job["manifest"]["draft"]["purpose"] != "comparison":
            raise Problem(422, "SCENARIO_REQUIRED", "意见与审核只绑定已完成的具体比较成果。")
        if lock:
            # Real write lock on SQLite and PostgreSQL; all mutations lock the same immutable run.
            c.execute(update(jobs).where(jobs.c.id == job_id).values(id=jobs.c.id))
        return job, role

    def draft(c, job_id, actor):
        row = (
            c.execute(
                select(opinion_drafts).where(
                    opinion_drafts.c.job_id == job_id, opinion_drafts.c.actor == actor
                )
            )
            .mappings()
            .first()
        )
        return (
            dict(row)
            if row
            else {"job_id": job_id, "actor": actor, "revision": 0, "text": "", "perspective": None}
        )

    def latest(c, job_id):
        row = (
            c.execute(
                select(reviews)
                .where(reviews.c.job_id == job_id)
                .order_by(reviews.c.revision.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )
        return dict(row) if row else {"revision": 0, "status": "unreviewed"}

    @routes.get("/api/jobs/{job_id}/discussion")
    def state(job_id: str, request: Request):
        with store.engine.connect() as c:
            job, role = require(c, request.state.actor["id"], job_id)
            return {
                "review": latest(c, job_id),
                "can_comment": role != "viewer",
                "can_review": role == "manager",
                "draft_revision": job["manifest"]["draft_revision"],
                "policy_decision": False,
                "business_validated": False,
            }

    @routes.get("/api/jobs/{job_id}/discussion/draft")
    def get_draft(job_id: str, request: Request):
        with store.engine.connect() as c:
            require(c, request.state.actor["id"], job_id, write=True)
            return draft(c, job_id, request.state.actor["id"])

    @routes.put("/api/jobs/{job_id}/discussion/draft")
    def save_draft(job_id: str, body: SaveOpinion, request: Request):
        actor = request.state.actor["id"]
        with store.engine.begin() as c:
            job, _ = require(c, actor, job_id, write=True, lock=True)
            old = draft(c, job_id, actor)
            if old["revision"] != body.expected_revision:
                raise Problem(
                    409,
                    "OPINION_DRAFT_CONFLICT",
                    "另一窗口已更新意见草稿；当前文字保留，请核对。",
                    {"remote": old},
                )
            values = {
                "text": body.text,
                "perspective": body.perspective,
                "revision": old["revision"] + 1,
            }
            if old["revision"]:
                c.execute(
                    update(opinion_drafts)
                    .where(opinion_drafts.c.job_id == job_id, opinion_drafts.c.actor == actor)
                    .values(**values)
                )
            else:
                c.execute(insert(opinion_drafts).values(job_id=job_id, actor=actor, **values))
            audit_event(c, actor, job["project_id"], "save_opinion_draft", job_id)
            return {**old, **values}

    @routes.post("/api/jobs/{job_id}/discussion/comments", status_code=201)
    def publish(job_id: str, body: PublishOpinion, request: Request):
        actor = request.state.actor["id"]
        with store.engine.begin() as c:
            job, role = require(c, actor, job_id, write=True, lock=True)
            old = (
                c.execute(
                    select(comments).where(
                        comments.c.job_id == job_id,
                        comments.c.actor == actor,
                        comments.c.idempotency_key == body.idempotency_key,
                    )
                )
                .mappings()
                .first()
            )
            if old:
                if old["origin_revision"] != body.expected_revision:
                    raise Problem(409, "IDEMPOTENCY_CONFLICT", "该提交标识已用于另一版本意见。")
                return dict(old)
            current = draft(c, job_id, actor)
            if current["revision"] != body.expected_revision:
                raise Problem(409, "OPINION_DRAFT_CONFLICT", "意见草稿已有变化，请先核对保存版本。")
            if not current["text"].strip() or current["perspective"] is None:
                raise Problem(
                    422, "OPINION_REQUIRED", "请填写意见并选择讨论视角；视角不会改变账号权限。"
                )
            row = {
                "id": identifier(),
                "job_id": job_id,
                "actor": actor,
                "author": request.state.actor["email"],
                "role": role,
                "origin_revision": current["revision"],
                "idempotency_key": body.idempotency_key,
                "text": current["text"],
                "perspective": current["perspective"],
                "created": time.time(),
            }
            c.execute(insert(comments).values(**row))
            c.execute(
                update(opinion_drafts)
                .where(opinion_drafts.c.job_id == job_id, opinion_drafts.c.actor == actor)
                .values(text="", revision=current["revision"] + 1)
            )
            audit_event(c, actor, job["project_id"], "publish_scenario_comment", row["id"])
            return row

    @routes.post("/api/jobs/{job_id}/discussion/reviews", status_code=201)
    def review(job_id: str, body: ReviewRequest, request: Request):
        actor = request.state.actor["id"]
        with store.engine.begin() as c:
            job, _ = require(c, actor, job_id, manage=True, lock=True)
            old = (
                c.execute(
                    select(reviews).where(
                        reviews.c.job_id == job_id,
                        reviews.c.actor == actor,
                        reviews.c.idempotency_key == body.idempotency_key,
                    )
                )
                .mappings()
                .first()
            )
            if old:
                if old["request"] != body.model_dump():
                    raise Problem(409, "IDEMPOTENCY_CONFLICT", "该提交标识已用于不同审核内容。")
                return dict(old)
            if latest(c, job_id)["revision"] != body.expected_revision:
                raise Problem(
                    409, "REVIEW_CONFLICT", "审核状态已有变化，请刷新核对；不会覆盖他人审核。"
                )
            if not body.note.strip():
                raise Problem(422, "REVIEW_NOTE_REQUIRED", "请说明技术审核依据。")
            row = {
                "id": identifier(),
                "job_id": job_id,
                "actor": actor,
                "author": request.state.actor["email"],
                "revision": body.expected_revision + 1,
                "status": body.status,
                "note": body.note,
                "idempotency_key": body.idempotency_key,
                "request": body.model_dump(),
                "created": time.time(),
            }
            c.execute(insert(reviews).values(**row))
            audit_event(c, actor, job["project_id"], "review_scenario", row["id"])
            return row

    def history(table, job_id, request, limit, offset):
        with store.engine.connect() as c:
            require(c, request.state.actor["id"], job_id)
            total = c.scalar(
                select(func.count()).select_from(table).where(table.c.job_id == job_id)
            )
            rows = c.execute(
                select(table)
                .where(table.c.job_id == job_id)
                .order_by(table.c.created.desc(), table.c.id.desc())
                .limit(limit)
                .offset(offset)
            ).mappings()
            return {
                "items": [dict(row) for row in rows],
                "total": total,
                "limit": limit,
                "offset": offset,
            }

    @routes.get("/api/jobs/{job_id}/discussion/comments")
    def list_comments(
        job_id: str,
        request: Request,
        limit: int = Query(25, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ):
        return history(comments, job_id, request, limit, offset)

    @routes.get("/api/jobs/{job_id}/discussion/reviews")
    def list_reviews(
        job_id: str,
        request: Request,
        limit: int = Query(25, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ):
        return history(reviews, job_id, request, limit, offset)

    return routes
