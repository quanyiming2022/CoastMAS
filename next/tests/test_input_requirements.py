"""Fixed methods drive input needs without mutating tasks or guessing file semantics."""

from test_method_library import create, definition, publish


def test_method_application_drives_requirements_and_plain_preview_remains_unblocked(workspace):
    _, _, client, project = workspace
    task = client.post(
        "/api/tasks",
        json={"project_id": project, "goal": "comprehensive-assessment", "title": "需求工程验证"},
    ).json()
    empty = client.get(f"/api/tasks/{task['id']}/input-requirements").json()
    assert empty["requirements"] == [] and empty["method"] is None
    config = definition()
    config["configuration"]["indicators"][0]["concept"] = "NDVI"
    method = publish(client, create(client, project, config))["template"]
    # Publication alone cannot change the research.
    assert client.get(f"/api/tasks/{task['id']}/input-requirements").json()["requirements"] == []
    applied = client.post(
        f"/api/tasks/{task['id']}/apply-method",
        json={"expected_revision": 1, "method_id": method["id"], "method_revision": 1},
    ).json()
    needed = client.get(f"/api/tasks/{task['id']}/input-requirements").json()
    assert len(needed["requirements"]) == 1
    assert needed["requirements"][0]["status"] == "missing"
    assert len(needed["requirements"][0]["alternatives"]) == 2
    assert client.get("/api/tasks/" + task["id"]).json() == applied
    # Matching filename and column spelling alone never approve an indicator.
    upload = client.post(
        f"/api/projects/{project}/assets", files={"file": ("NDVI.csv", b"NDVI\n0.5\n")}
    )
    assert upload.status_code == 201
    assert (
        client.get(f"/api/tasks/{task['id']}/input-requirements").json()["requirements"][0][
            "status"
        ]
        == "missing"
    )


def test_analyst_can_publish_but_cannot_approve_or_apply_unapproved_version(workspace):
    _, store, client, project = workspace
    admin = client.get("/api/session").json()["id"]
    analyst = store.create_account("analyst@example.test", "separate-role-password")
    store.set_member(admin, project, analyst, "analyst")
    session = client.post(
        "/api/session", json={"email": "analyst@example.test", "password": "separate-role-password"}
    ).json()
    client.headers["X-CSRF-Token"] = session["csrf"]
    draft = create(client, project)
    denied = client.post(
        f"/api/method-workspaces/{draft['id']}/publish",
        json={"expected_revision": 1, "approve": True},
    )
    assert denied.status_code == 403
    assert client.get(f"/api/method-workspaces/{draft['id']}").json()["publication"] is None
    published = client.post(
        f"/api/method-workspaces/{draft['id']}/publish",
        json={"expected_revision": 1, "approve": False},
    )
    assert published.status_code == 201, published.text
    method = published.json()["template"]
    assert method["approved"] is False
    assert (
        client.post(f"/api/templates/{method['id']}/approve", json={"revision": 1}).status_code
        == 403
    )
    task = client.post(
        "/api/tasks",
        json={"project_id": project, "goal": "comprehensive-assessment", "title": "未批准不能应用"},
    ).json()
    assert (
        client.post(
            f"/api/tasks/{task['id']}/apply-method",
            json={"expected_revision": 1, "method_id": method["id"], "method_revision": 1},
        ).status_code
        == 422
    )


def test_model_requirements_distinguish_training_prediction_and_clustering(workspace):
    _, _, client, project = workspace
    for purpose in ("cluster", "regression"):
        task = client.post(
            "/api/tasks", json={"project_id": project, "purpose": purpose, "title": "角色核对"}
        ).json()
        needs = client.get(f"/api/tasks/{task['id']}/input-requirements").json()
        roles = {r["id"] for r in needs["requirements"]}
        assert "predictors" in roles
        assert ("response" in roles) == (purpose == "regression")
        if purpose == "regression":
            task = client.put(
                "/api/tasks/" + task["id"],
                json={
                    "expected_revision": 1,
                    "draft": {**task["draft"], "options": {"model_operation": "predict"}},
                },
            ).json()
            prediction = client.get(f"/api/tasks/{task['id']}/input-requirements").json()
            roles = {r["id"] for r in prediction["requirements"]}
            assert "response" not in roles and "fitted_model" in roles
            assert prediction["execution_status"] == "not_implemented"


def test_ndvi_recipe_cannot_claim_nonexistent_bands_ready(workspace):
    _, _, client, project = workspace
    task = client.post(
        "/api/tasks",
        json={"project_id": project, "goal": "comprehensive-assessment", "title": "NDVI核对"},
    ).json()
    config = definition()
    config["configuration"]["indicators"][0]["concept"] = "NDVI"
    method = publish(client, create(client, project, config))["template"]
    task = client.post(
        f"/api/tasks/{task['id']}/apply-method",
        json={"expected_revision": 1, "method_id": method["id"], "method_revision": 1},
    ).json()
    client.put(
        "/api/tasks/" + task["id"],
        json={
            "expected_revision": task["revision"],
            "draft": {
                **task["draft"],
                "options": {
                    **task["draft"]["options"],
                    "preparation": {
                        "ndvi": {
                            "asset_id": "not-real",
                            "red_band": 1,
                            "nir_band": 4,
                            "qa_policy": "source_mask",
                        }
                    },
                },
            },
        },
    )
    needs = client.get(f"/api/tasks/{task['id']}/input-requirements").json()
    assert needs["requirements"][0]["status"] == "missing"
    assert needs["requirements"][0]["alternatives"][1]["state"] == "needs_band_mapping"
