from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from coastmas.core.errors import CoastMASError
from coastmas.persistence.jobs import cancel_job, claim_job, publish_result, read_job, submit_job


def test_idempotent_submit_and_duplicate_delivery(engine, actors):
    user, viewer, outsider, project = actors
    key = str(uuid4())
    with Session(engine) as session, session.begin():
        first = submit_job(
            session, user_id=user, project_id=project, idempotency_key=key, manifest={"input": 1}
        )
        second = submit_job(
            session, user_id=user, project_id=project, idempotency_key=key, manifest={"input": 1}
        )
        assert first.id == second.id
        with pytest.raises(CoastMASError, match="conflict"):
            submit_job(
                session,
                user_id=user,
                project_id=project,
                idempotency_key=key,
                manifest={"input": 2},
            )
    with Session(engine) as session, session.begin():
        token = claim_job(session, first.id, lease_seconds=60)
        assert token is not None
    with Session(engine) as session, session.begin():
        assert claim_job(session, first.id, lease_seconds=60) is None
        with pytest.raises(CoastMASError, match="permission"):
            read_job(session, user_id=outsider, job_id=first.id)


def test_cancellation_blocks_late_publication(engine, actors):
    user, viewer, outsider, project = actors
    with Session(engine) as session, session.begin():
        job = submit_job(
            session,
            user_id=user,
            project_id=project,
            idempotency_key=str(uuid4()),
            manifest={"input": 1},
        )
        token = claim_job(session, job.id, lease_seconds=60)
    with Session(engine) as session, session.begin():
        cancel_job(session, user_id=user, job_id=job.id)
        current = read_job(session, user_id=user, job_id=job.id)
        assert current.cancel_requested
        assert current.status == "RUNNING"
    with Session(engine) as session, session.begin():
        assert not publish_result(
            session,
            job_id=job.id,
            worker_token=token,
            manifest={"checksum": "a" * 64, "uri": "s3://coastmas/result"},
        )
        assert read_job(session, user_id=user, job_id=job.id).status == "CANCELLED"


def test_publish_is_once_only_and_stale_worker_cannot_publish(engine, actors):
    user, viewer, outsider, project = actors
    with Session(engine) as session, session.begin():
        job = submit_job(
            session,
            user_id=user,
            project_id=project,
            idempotency_key=str(uuid4()),
            manifest={"input": 1},
        )
        token = claim_job(session, job.id, lease_seconds=60)
    with Session(engine) as session, session.begin():
        assert not publish_result(
            session, job_id=job.id, worker_token="stale", manifest={"value": 999}
        )
        assert publish_result(session, job_id=job.id, worker_token=token, manifest={"value": 42})
        assert not publish_result(
            session, job_id=job.id, worker_token=token, manifest={"value": 99}
        )
        assert read_job(session, user_id=viewer, job_id=job.id).status == "SUCCEEDED"


def test_concurrent_identical_submission_has_one_job(engine, actors):
    from concurrent.futures import ThreadPoolExecutor

    user, viewer, outsider, project = actors
    key = str(uuid4())

    def submit():
        with Session(engine) as session, session.begin():
            return submit_job(
                session,
                user_id=user,
                project_id=project,
                idempotency_key=key,
                manifest={"input": 7},
            ).id

    with ThreadPoolExecutor(max_workers=4) as pool:
        identifiers = list(pool.map(lambda _: submit(), range(8)))
    assert len(set(identifiers)) == 1


def test_expired_lease_recovery_rejects_original_worker(engine, actors):
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import update

    from coastmas.persistence.schema import Job

    user, viewer, outsider, project = actors
    with Session(engine) as session, session.begin():
        job = submit_job(
            session,
            user_id=user,
            project_id=project,
            idempotency_key=str(uuid4()),
            manifest={"input": 1},
        )
        old_token = claim_job(session, job.id, lease_seconds=60)
    with Session(engine) as session, session.begin():
        session.execute(
            update(Job)
            .where(Job.id == job.id)
            .values(lease_until=datetime.now(UTC) - timedelta(seconds=1))
        )
    with Session(engine) as session, session.begin():
        new_token = claim_job(session, job.id, lease_seconds=60)
        assert new_token and new_token != old_token
        assert not publish_result(
            session, job_id=job.id, worker_token=old_token, manifest={"stale": True}
        )
        assert publish_result(
            session, job_id=job.id, worker_token=new_token, manifest={"fresh": True}
        )


def test_heartbeat_and_failure_respect_worker_ownership(engine, actors):
    from coastmas.persistence.jobs import finish_failed_job, heartbeat_job

    user, _, _, project = actors
    with Session(engine) as session, session.begin():
        job = submit_job(
            session, user_id=user, project_id=project, idempotency_key=str(uuid4()), manifest={}
        )
        token = claim_job(session, job.id, lease_seconds=60)
    with Session(engine) as session, session.begin():
        assert not heartbeat_job(session, job.id, "stale", lease_seconds=60, progress=0.9)
        assert heartbeat_job(session, job.id, token, lease_seconds=60, progress=0.5)
        assert heartbeat_job(session, job.id, token, lease_seconds=60, progress=0.2)
        assert read_job(session, user_id=user, job_id=job.id).progress == 0.5
        assert not finish_failed_job(session, job.id, "stale", code="ERROR", message="failure")
        assert finish_failed_job(session, job.id, token, code="MODEL_ERROR", message="model failed")
        assert read_job(session, user_id=user, job_id=job.id).status == "FAILED"


def test_cancel_acknowledged_only_by_current_worker(engine, actors):
    from coastmas.persistence.jobs import finish_failed_job, heartbeat_job

    user, _, _, project = actors
    with Session(engine) as session, session.begin():
        job = submit_job(
            session, user_id=user, project_id=project, idempotency_key=str(uuid4()), manifest={}
        )
        token = claim_job(session, job.id, lease_seconds=60)
    with Session(engine) as session, session.begin():
        cancel_job(session, user_id=user, job_id=job.id)
        assert not heartbeat_job(session, job.id, token, lease_seconds=60, progress=0.5)
        assert finish_failed_job(session, job.id, token, code="CANCELLED", message="stopped")
        assert read_job(session, user_id=user, job_id=job.id).status == "CANCELLED"


def test_published_result_checks_current_permission_on_every_read(engine, actors):
    from sqlalchemy import delete

    from coastmas.persistence.jobs import read_result
    from coastmas.persistence.schema import Membership

    user, viewer, outsider, project = actors
    with Session(engine) as session, session.begin():
        job = submit_job(
            session, user_id=user, project_id=project, idempotency_key=str(uuid4()), manifest={}
        )
        token = claim_job(session, job.id, lease_seconds=60)
        publish_result(session, job_id=job.id, worker_token=token, manifest={"value": 42})
        assert read_result(session, user_id=viewer, job_id=job.id) == {"value": 42}
        session.execute(
            delete(Membership).where(Membership.project_id == project, Membership.user_id == viewer)
        )
    with Session(engine) as session:
        for actor in (viewer, outsider):
            with pytest.raises(CoastMASError):
                read_result(session, user_id=actor, job_id=job.id)
