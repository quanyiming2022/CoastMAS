"""Discussion belongs to immutable runs, never silently validates policy or science."""

from coastmas_next.app import create_app
from coastmas_next.worker import Worker
from fastapi.testclient import TestClient
from test_comparison import comparison_task, completed_assessment


def scenario(store, client, project):
    ids = completed_assessment(store, client, project)
    task = comparison_task(client, project, ids)
    run = client.post(
        f"/api/tasks/{task['id']}/execute",
        json={"expected_revision": task["revision"], "idempotency_key": "scenario"},
    ).json()
    assert Worker(store).run_once()
    return task, run["id"]


def signin(settings, email):
    client = TestClient(create_app(settings))
    result = client.post(
        "/api/session", json={"email": email, "password": "safe-password-for-tests"}
    ).json()
    client.headers["X-CSRF-Token"] = result["csrf"]
    return client


def test_durable_personal_opinion_draft_cas_publish_and_replay(workspace):
    _, store, client, project = workspace
    _, job = scenario(store, client, project)
    base = f"/api/jobs/{job}/discussion"
    first = client.get(base + "/draft")
    assert first.status_code == 200, first.text
    assert first.json()["revision"] == 0
    body = {"expected_revision": 0, "text": "请核对参考范围和保护约束。", "perspective": "research"}
    saved = client.put(base + "/draft", json=body)
    assert saved.status_code == 200
    assert client.get(base + "/draft").json()["text"] == body["text"]
    assert client.put(base + "/draft", json={**body, "text": "stale overwrite"}).status_code == 409
    posted = client.post(
        base + "/comments", json={"expected_revision": 1, "idempotency_key": "publish-one"}
    )
    assert posted.status_code == 201, posted.text
    replay = client.post(
        base + "/comments", json={"expected_revision": 1, "idempotency_key": "publish-one"}
    )
    assert replay.json()["id"] == posted.json()["id"]
    assert client.get(base + "/comments").json()["total"] == 1
    assert client.get(base + "/draft").json()["text"] == ""
    assert client.get(base + "/draft").json()["revision"] == 2
    conflict = client.post(
        base + "/comments", json={"expected_revision": 2, "idempotency_key": "publish-one"}
    )
    assert conflict.status_code == 409


def test_roles_personal_drafts_review_version_conflict_and_history_retained(workspace):
    settings, store, client, project = workspace
    task, job = scenario(store, client, project)
    owner = client.get("/api/session").json()["id"]
    analyst_id = store.create_account("analyst@example.test", "safe-password-for-tests")
    store.set_member(owner, project, analyst_id, "analyst")
    analyst = signin(settings, "analyst@example.test")
    viewer = signin(settings, "viewer@example.test")
    base = f"/api/jobs/{job}/discussion"
    assert (
        client.put(
            base + "/draft",
            json={"expected_revision": 0, "text": "owner draft", "perspective": "management"},
        ).status_code
        == 200
    )
    assert analyst.get(base + "/draft").json()["text"] == ""
    state = viewer.get(base).json()
    assert state["can_comment"] is False and state["can_review"] is False
    assert (
        viewer.put(
            base + "/draft",
            json={"expected_revision": 0, "text": "forbidden", "perspective": "public"},
        ).status_code
        == 403
    )
    review = {
        "expected_revision": 0,
        "status": "reviewed",
        "note": "技术结果已核对，不构成政策批准。",
        "idempotency_key": "review-one",
    }
    assert analyst.post(base + "/reviews", json=review).status_code == 403
    approved = client.post(base + "/reviews", json=review)
    assert approved.status_code == 201, approved.text
    assert client.post(base + "/reviews", json=review).json()["id"] == approved.json()["id"]
    assert (
        client.post(base + "/reviews", json={**review, "idempotency_key": "concurrent"}).status_code
        == 409
    )
    assert (
        client.post(
            base + "/reviews",
            json={
                **review,
                "expected_revision": 1,
                "status": "changes_requested",
                "idempotency_key": "review-two",
            },
        ).status_code
        == 201
    )
    assert client.get(base).json()["review"]["status"] == "changes_requested"
    history = client.get(base + "/reviews").json()
    assert history["total"] == 2
    assert history["items"][1]["status"] == "reviewed"
    task["draft"]["title"] = "Revised scenario title"
    assert (
        client.put(
            f"/api/tasks/{task['id']}",
            json={"expected_revision": task["revision"], "draft": task["draft"]},
        ).status_code
        == 200
    )
    assert client.get(base).json()["review"]["status"] == "changes_requested"
    result = client.get(f"/api/jobs/{job}/result").json()
    assert not result["states"]["business_validated"]
    outsider = store.create_account("outside-review@example.test", "safe-password-for-tests")
    store.create_project(outsider, "other")
    foreign = signin(settings, "outside-review@example.test")
    assert foreign.get(base).status_code == 404
    assert foreign.get(base + "/comments").status_code == 404


def test_new_run_never_inherits_old_review_and_concurrent_reviews_do_not_overwrite(workspace):
    from concurrent.futures import ThreadPoolExecutor

    settings, store, client, project = workspace
    task, job = scenario(store, client, project)
    reviewers = [signin(settings, "admin@example.test"), signin(settings, "admin@example.test")]

    def submit(index):
        return reviewers[index].post(
            f"/api/jobs/{job}/discussion/reviews",
            json={
                "expected_revision": 0,
                "status": "reviewed",
                "note": f"Independent review {index}",
                "idempotency_key": f"concurrent-review-{index}",
            },
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        replies = list(pool.map(submit, [0, 1]))
    assert sorted(r.status_code for r in replies) == [201, 409]
    assert client.get(f"/api/jobs/{job}/discussion/reviews").json()["total"] == 1
    task["draft"]["title"] = "A new version requiring its own review"
    saved = client.put(
        f"/api/tasks/{task['id']}",
        json={"expected_revision": task["revision"], "draft": task["draft"]},
    ).json()
    new = client.post(
        f"/api/tasks/{task['id']}/execute",
        json={"expected_revision": saved["revision"], "idempotency_key": "new-version"},
    ).json()
    assert Worker(store).run_once()
    assert client.get(f"/api/jobs/{new['id']}/discussion").json()["review"] == {
        "revision": 0,
        "status": "unreviewed",
    }
    assert client.get(f"/api/jobs/{job}/discussion").json()["review"]["status"] == "reviewed"
