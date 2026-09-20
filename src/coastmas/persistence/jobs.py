"""Transactional job leases, idempotent submission, cancellation and publication.

A running cancel is a request until the worker acknowledges it. Publication
checks the request while holding the same row lock used by cancellation.
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from pydantic import JsonValue
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from coastmas.core.errors import CoastMASError
from coastmas.persistence.resources import fingerprint, require_permission
from coastmas.persistence.schema import AuditLog, Job, ResultBundle


@dataclass(frozen=True)
class JobRecord:
    id: str
    project_id: str
    submitted_by: str
    status: str
    cancel_requested: bool
    progress: float
    attempt: int
    manifest: dict[str, JsonValue]
    error: dict[str, JsonValue] | None


def snapshot(job: Job) -> JobRecord:
    manifest: dict[str, JsonValue] = json.loads(json.dumps(job.manifest, allow_nan=False))
    return JobRecord(
        job.id,
        job.project_id,
        job.submitted_by,
        job.status,
        job.cancel_requested,
        job.progress,
        job.attempt,
        manifest,
        job.error,
    )


def submit_job(
    session: Session,
    *,
    user_id: str,
    project_id: str,
    idempotency_key: str,
    manifest: dict[str, JsonValue],
) -> JobRecord:
    require_permission(session, user_id, project_id, "write")
    if not idempotency_key or len(idempotency_key) > 256:
        raise CoastMASError("VALIDATION_ERROR", "idempotency key required, maximum 256 characters")
    checksum = fingerprint(manifest)
    identifier = str(uuid4())
    statement = (
        insert(Job)
        .values(
            id=identifier,
            project_id=project_id,
            submitted_by=user_id,
            idempotency_key=idempotency_key,
            fingerprint=checksum,
            manifest=manifest,
        )
        .on_conflict_do_nothing(index_elements=["project_id", "submitted_by", "idempotency_key"])
    )
    session.execute(statement)
    job = session.scalar(
        select(Job).where(
            Job.project_id == project_id,
            Job.submitted_by == user_id,
            Job.idempotency_key == idempotency_key,
        )
    )
    if job is None:
        raise CoastMASError("EXECUTION_ERROR", "submitted job could not be read")
    if job.fingerprint != checksum:
        raise CoastMASError("IDEMPOTENCY_CONFLICT", "idempotency key conflict: different input")
    if job.id == identifier:
        session.add(
            AuditLog(
                id=str(uuid4()),
                who=user_id,
                action="SUBMIT",
                resource=job.id,
                old_value=None,
                new_value={"fingerprint": checksum},
            )
        )
    session.flush()
    return snapshot(job)


def read_job(session: Session, *, user_id: str, job_id: str) -> JobRecord:
    job = session.get(Job, job_id)
    if job is None:
        raise CoastMASError("AUTHORIZATION_ERROR", "permission denied or job unavailable")
    require_permission(session, user_id, job.project_id, "read")
    return snapshot(job)


def claim_job(session: Session, job_id: str, *, lease_seconds: int) -> str | None:
    if not 1 <= lease_seconds <= 3600:
        raise CoastMASError("VALIDATION_ERROR", "lease duration outside supported range")
    job = session.scalar(select(Job).where(Job.id == job_id).with_for_update())
    if job is None or job.status in {"SUCCEEDED", "FAILED", "CANCELLED"}:
        return None
    now = datetime.now(UTC)
    if job.status == "RUNNING" and job.lease_until is not None and job.lease_until > now:
        return None
    if job.cancel_requested:
        job.status = "CANCELLED"
        job.finished_at = now
        session.flush()
        return None
    if job.attempt >= 3:
        job.status = "FAILED"
        job.error = {"error_code": "LEASE_EXHAUSTED", "message": "worker lease retry limit reached"}
        job.finished_at = now
        session.flush()
        return None
    token = str(uuid4())
    job.status = "RUNNING"
    job.worker_token = token
    job.lease_until = now + timedelta(seconds=lease_seconds)
    job.attempt += 1
    job.started_at = job.started_at or now
    session.flush()
    return token


def cancel_job(session: Session, *, user_id: str, job_id: str) -> None:
    job = session.scalar(select(Job).where(Job.id == job_id).with_for_update())
    if job is None:
        raise CoastMASError("AUTHORIZATION_ERROR", "permission denied or job unavailable")
    require_permission(session, user_id, job.project_id, "write")
    if job.status in {"SUCCEEDED", "FAILED", "CANCELLED"}:
        return
    job.cancel_requested = True
    if job.status == "QUEUED":
        job.status = "CANCELLED"
        job.finished_at = datetime.now(UTC)
    session.add(
        AuditLog(
            id=str(uuid4()),
            who=user_id,
            action="CANCEL_REQUEST",
            resource=job.id,
            old_value=None,
            new_value={"cancel_requested": True},
        )
    )
    session.flush()


def publish_result(
    session: Session,
    *,
    job_id: str,
    worker_token: str,
    manifest: dict[str, JsonValue],
    result_id: str | None = None,
) -> bool:
    job = session.scalar(select(Job).where(Job.id == job_id).with_for_update())
    now = datetime.now(UTC)
    if (
        job is None
        or job.status != "RUNNING"
        or job.worker_token != worker_token
        or job.lease_until is None
        or job.lease_until <= now
    ):
        return False
    if job.cancel_requested:
        job.status = "CANCELLED"
        job.finished_at = now
        session.flush()
        return False
    require_permission(session, job.submitted_by, job.project_id, "write")
    session.add(
        ResultBundle(
            id=result_id or str(uuid4()),
            job_id=job.id,
            manifest=manifest,
            checksum=fingerprint(manifest),
        )
    )
    job.status = "SUCCEEDED"
    job.progress = 1
    job.finished_at = now
    session.add(
        AuditLog(
            id=str(uuid4()),
            who=job.submitted_by,
            action="PUBLISH_RESULT",
            resource=job.id,
            old_value={"status": "RUNNING"},
            new_value={"status": "SUCCEEDED"},
        )
    )
    session.flush()
    return True


def heartbeat_job(
    session: Session, job_id: str, worker_token: str, *, lease_seconds: int, progress: float
) -> bool:
    """Extend only a live owned lease; False tells the process runner to stop."""
    if not 1 <= lease_seconds <= 3600 or not 0 <= progress < 1:
        raise CoastMASError("VALIDATION_ERROR", "invalid heartbeat lease or progress")
    job = session.scalar(select(Job).where(Job.id == job_id).with_for_update())
    now = datetime.now(UTC)
    if (
        job is None
        or job.status != "RUNNING"
        or job.worker_token != worker_token
        or job.lease_until is None
        or job.lease_until <= now
        or job.cancel_requested
    ):
        return False
    require_permission(session, job.submitted_by, job.project_id, "write")
    job.lease_until = now + timedelta(seconds=lease_seconds)
    job.progress = max(job.progress, progress)
    session.flush()
    return True


def finish_failed_job(
    session: Session, job_id: str, worker_token: str, *, code: str, message: str
) -> bool:
    """A stopped worker may acknowledge cancellation but cannot revive a stale lease."""
    job = session.scalar(select(Job).where(Job.id == job_id).with_for_update())
    now = datetime.now(UTC)
    if (
        job is None
        or job.status != "RUNNING"
        or job.worker_token != worker_token
        or job.lease_until is None
        or job.lease_until <= now
    ):
        return False
    job.status = "CANCELLED" if job.cancel_requested else "FAILED"
    job.error = {"error_code": code, "message": message}
    job.finished_at = now
    session.add(
        AuditLog(
            id=str(uuid4()),
            who=job.submitted_by,
            action=job.status,
            resource=job.id,
            old_value={"status": "RUNNING"},
            new_value={"error_code": code},
        )
    )
    session.flush()
    return True


def read_result(session: Session, *, user_id: str, job_id: str) -> dict[str, JsonValue]:
    read_job(session, user_id=user_id, job_id=job_id)
    result = session.scalar(select(ResultBundle).where(ResultBundle.job_id == job_id))
    if result is None:
        raise CoastMASError("RESULT_UNAVAILABLE", "job has no published result")
    if fingerprint(result.manifest) != result.checksum:
        raise CoastMASError("CHECKSUM_ERROR", "result manifest integrity check failed")
    snapshot: dict[str, JsonValue] = json.loads(json.dumps(result.manifest, allow_nan=False))
    return snapshot
