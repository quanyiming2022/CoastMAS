"""One durable trace across parse/recommend/build; no hidden provider budget reset.

Reservations conservatively consume capacity even after an uncertain crash. They
are not reported as confirmed HTTP calls or fabricated token consumption. The
provider must commit reservation/dispatch evidence BEFORE sending a request.
"""

from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import JsonValue
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from coastmas.core.errors import CoastMASError
from coastmas.persistence.resources import fingerprint, require_permission
from coastmas.persistence.schema import PlanningTrace, ProviderRequest


def read_trace(
    session: Session, user_id: str, trace_id: str, *, lock: bool = False
) -> PlanningTrace:
    query = select(PlanningTrace).where(PlanningTrace.id == trace_id)
    if lock:
        query = query.with_for_update()
    trace = session.scalar(query.execution_options(populate_existing=True))
    if trace is None or trace.owner_id != user_id:
        raise CoastMASError("AUTHORIZATION_ERROR", "planning trace unavailable")
    require_permission(session, user_id, trace.project_id, "write" if lock else "read")
    return trace


def create_trace(
    session: Session,
    user_id: str,
    project_id: str,
    *,
    key: str,
    inputs: dict[str, JsonValue],
    allow_external: bool,
    max_provider_requests: int = 2,
) -> PlanningTrace:
    require_permission(session, user_id, project_id, "write")
    if not key.strip() or len(key) > 256:
        raise CoastMASError("PLAN_INVALID", "idempotency key must contain 1 to 256 characters")
    if isinstance(max_provider_requests, bool) or not 0 <= max_provider_requests <= 32:
        raise CoastMASError("PLAN_INVALID", "provider request limit is outside server bounds")
    identity: dict[str, JsonValue] = {
        "inputs": inputs,
        "allow_external": allow_external,
        "max_provider_requests": max_provider_requests,
    }
    checksum = fingerprint(identity)
    session.execute(
        insert(PlanningTrace)
        .values(
            id=str(uuid4()),
            project_id=project_id,
            owner_id=user_id,
            idempotency_key=key,
            inputs=inputs,
            fingerprint=checksum,
            allow_external=allow_external,
            max_provider_requests=max_provider_requests,
            reserved_requests=0,
        )
        .on_conflict_do_nothing(index_elements=["project_id", "owner_id", "idempotency_key"])
    )
    trace = session.scalar(
        select(PlanningTrace)
        .where(
            PlanningTrace.project_id == project_id,
            PlanningTrace.owner_id == user_id,
            PlanningTrace.idempotency_key == key,
        )
        .execution_options(populate_existing=True)
    )
    if trace is None:
        raise CoastMASError("PLAN_CONFLICT", "planning trace insert did not become visible")
    if trace.fingerprint != checksum:
        raise CoastMASError(
            "IDEMPOTENCY_CONFLICT", "key already used for different planning inputs"
        )
    return trace


def reserve_request(
    session: Session,
    user_id: str,
    trace_id: str,
    *,
    request_fingerprint: str,
    provider_model: str | None = None,
    provider_endpoint: str | None = None,
) -> ProviderRequest:
    trace = read_trace(session, user_id, trace_id, lock=True)
    if not trace.allow_external:
        raise CoastMASError("EXTERNAL_NOT_AUTHORIZED", "external planning has not been authorized")
    if trace.artifact is not None:
        raise CoastMASError("PLAN_FINALIZED", "planning artifact is already finalized")
    if trace.reserved_requests >= trace.max_provider_requests:
        raise CoastMASError("PLAN_BUDGET_EXHAUSTED", "shared planning request budget exhausted")
    if len(request_fingerprint) != 64 or any(
        c not in "0123456789abcdef" for c in request_fingerprint
    ):
        raise CoastMASError("PLAN_INVALID", "request fingerprint must be SHA-256")
    trace.reserved_requests += 1
    request = ProviderRequest(
        id=str(uuid4()),
        trace_id=trace_id,
        ordinal=trace.reserved_requests,
        request_fingerprint=request_fingerprint,
        provider_model=provider_model,
        provider_endpoint=provider_endpoint,
        status="RESERVED",
    )
    session.add(request)
    session.flush()
    return request


def mark_dispatched(session: Session, user_id: str, request_id: str) -> None:
    request = session.scalar(
        select(ProviderRequest)
        .where(
            ProviderRequest.id == request_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if request is None:
        raise CoastMASError("PLAN_INVALID", "provider reservation unavailable")
    trace = read_trace(session, user_id, request.trace_id)
    require_permission(session, user_id, trace.project_id, "write")
    if request.status != "RESERVED":
        raise CoastMASError("PLAN_CONFLICT", "reservation cannot dispatch twice")
    request.status = "DISPATCHED"
    request.dispatched_at = datetime.now(UTC)
    session.flush()


def finish_request(
    session: Session,
    request_id: str,
    *,
    status: Literal["SUCCEEDED", "INVALID", "FAILED"],
    response_fingerprint: str | None,
    usage: dict[str, JsonValue] | None,
    error_code: str | None,
    response_model: str | None = None,
    http_status: int | None = None,
) -> ProviderRequest:
    """Trusted provider completion path, retained even if owner access was revoked."""
    request = session.scalar(
        select(ProviderRequest)
        .where(
            ProviderRequest.id == request_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if request is None:
        raise CoastMASError("PLAN_INVALID", "provider request unavailable")
    if request.finished_at is not None:
        if (
            request.status,
            request.response_fingerprint,
            request.usage,
            request.error_code,
            request.response_model,
            request.http_status,
        ) != (
            status,
            response_fingerprint,
            usage,
            error_code,
            response_model,
            http_status,
        ):
            raise CoastMASError("IMMUTABLE_CONFLICT", "provider evidence already finalized")
        return request
    request.http_status = http_status
    request.response_model = response_model
    request.status = status
    request.response_fingerprint = response_fingerprint
    request.usage = usage
    request.error_code = error_code
    request.finished_at = datetime.now(UTC)
    session.flush()
    return request


def save_artifact(
    session: Session,
    user_id: str,
    trace_id: str,
    artifact: dict[str, JsonValue],
) -> PlanningTrace:
    trace = read_trace(session, user_id, trace_id, lock=True)
    if trace.artifact is not None and trace.artifact != artifact:
        raise CoastMASError("IMMUTABLE_CONFLICT", "planning artifact already finalized")
    trace.artifact = artifact
    session.flush()
    return trace
