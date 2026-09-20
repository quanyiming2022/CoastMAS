from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from coastmas.core.errors import CoastMASError
from coastmas.persistence.planning import (
    create_trace,
    finish_request,
    read_trace,
    reserve_request,
)
from coastmas.persistence.schema import Membership


def trace(engine, actors, *, allowed=True):
    owner, _, _, project = actors
    with Session(engine) as session, session.begin():
        record = create_trace(
            session,
            owner,
            project,
            key=str(uuid4()),
            inputs={"scene_version": 1},
            allow_external=allowed,
        )
        return record.id


def test_shared_plan_budget_is_atomic_under_concurrent_endpoints(engine, actors):
    identifier = trace(engine, actors)
    owner = actors[0]

    def reserve(_):
        try:
            with Session(engine) as session, session.begin():
                return reserve_request(session, owner, identifier, request_fingerprint="a" * 64).id
        except CoastMASError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(reserve, range(8)))
    assert results.count("PLAN_BUDGET_EXHAUSTED") == 6
    assert len(set(item for item in results if item != "PLAN_BUDGET_EXHAUSTED")) == 2
    with Session(engine) as session:
        saved = read_trace(session, owner, identifier)
        assert saved.reserved_requests == saved.max_provider_requests == 2


def test_trace_idempotency_is_scoped_and_cannot_reset_budget(engine, actors):
    owner, _, outsider, project = actors
    key = str(uuid4())
    with Session(engine) as session, session.begin():
        first = create_trace(
            session, owner, project, key=key, inputs={"scene_version": 1}, allow_external=True
        )
        identifier = first.id
        reserve_request(session, owner, identifier, request_fingerprint="b" * 64)
    with Session(engine) as session, session.begin():
        repeated = create_trace(
            session, owner, project, key=key, inputs={"scene_version": 1}, allow_external=True
        )
        assert repeated.id == identifier and repeated.reserved_requests == 1
        with pytest.raises(CoastMASError, match="different"):
            create_trace(
                session, owner, project, key=key, inputs={"scene_version": 2}, allow_external=True
            )
    with Session(engine) as session:
        with pytest.raises(CoastMASError):
            read_trace(session, outsider, identifier)


def test_external_consent_and_fresh_permissions_are_required(engine, actors):
    owner, _, _, project = actors
    denied = trace(engine, actors, allowed=False)
    allowed = trace(engine, actors)
    with Session(engine) as session, session.begin():
        with pytest.raises(CoastMASError, match="authorized"):
            reserve_request(session, owner, denied, request_fingerprint="a" * 64)
        read_trace(session, owner, allowed)
        with Session(engine) as revoke, revoke.begin():
            revoke.get(Membership, (project, owner)).role = "VIEWER"
        with pytest.raises(CoastMASError):
            reserve_request(session, owner, allowed, request_fingerprint="a" * 64)


def test_request_evidence_is_write_once_and_unknown_usage_stays_null(engine, actors):
    identifier = trace(engine, actors)
    with Session(engine) as session, session.begin():
        request = reserve_request(session, actors[0], identifier, request_fingerprint="a" * 64)
        request_id = request.id
    with Session(engine) as session, session.begin():
        finished = finish_request(
            session,
            request_id,
            status="FAILED",
            response_fingerprint=None,
            usage=None,
            error_code="PROVIDER_TIMEOUT",
        )
        assert finished.usage is None
        same = finish_request(
            session,
            request_id,
            status="FAILED",
            response_fingerprint=None,
            usage=None,
            error_code="PROVIDER_TIMEOUT",
        )
        assert same.id == request_id
        with pytest.raises(CoastMASError):
            finish_request(
                session,
                request_id,
                status="SUCCEEDED",
                response_fingerprint="b" * 64,
                usage={"input_tokens": 10},
                error_code=None,
            )
