"""Expired owners and cancellation requests must never publish stale results."""

import json
import time

from coastmas_next.execution import jobs
from coastmas_next.worker import Worker
from sqlalchemy import update
from test_execution import inspection_task


def enqueue(client, project):
    task, _ = inspection_task(client, project)
    return client.post(
        f"/api/tasks/{task['id']}/execute",
        json={"expected_revision": task["revision"], "idempotency_key": "recovery"},
    ).json()


def test_cancelled_abandoned_lease_is_finalized_without_compute(workspace, monkeypatch):
    _, store, client, project = workspace
    job = enqueue(client, project)
    owned = Worker(store).claim()
    assert owned["id"] == job["id"]
    assert client.post(f"/api/jobs/{job['id']}/cancel").status_code == 200
    with store.engine.begin() as connection:
        connection.execute(
            update(jobs).where(jobs.c.id == job["id"]).values(lease_until=time.time() - 1)
        )
    worker = Worker(store)

    def unexpected(*args, **kwargs):
        raise AssertionError("Cancelled work must not be computed")

    monkeypatch.setattr(worker, "compute", unexpected)
    worker.run_once()
    actual = client.get(f"/api/jobs/{job['id']}").json()
    assert actual["status"] == "cancelled"
    assert actual["finished"] is not None
    assert actual["output_key"] is None
    assert client.get(f"/api/jobs/{job['id']}/result").status_code == 409


def test_expired_owner_cannot_overwrite_recovered_output(workspace, monkeypatch):
    settings, store, client, project = workspace
    job = enqueue(client, project)
    first = Worker(store)
    stale = first.claim()
    with store.engine.begin() as connection:
        connection.execute(
            update(jobs).where(jobs.c.id == job["id"]).values(lease_until=time.time() - 1)
        )
    assert Worker(store).run_once()
    latest = client.get(f"/api/jobs/{job['id']}").json()
    assert latest["status"] == "succeeded"
    output = settings.storage_root / latest["output_key"]
    original = output.read_bytes()
    monkeypatch.setattr(first, "claim", lambda: stale)
    assert first.run_once()
    assert output.read_bytes() == original
    assert client.get(f"/api/jobs/{job['id']}").json()["lease"] == latest["lease"]
    assert list((settings.storage_root / "results").glob("*.json")) == [output]
    assert json.loads(original)["data"]["datasets"][0]["facts"]["layers"][0]["row_count"] == 2
