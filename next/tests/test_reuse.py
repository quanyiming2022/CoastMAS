"""Approved knowledge crosses batches; values and task bindings do not."""


def upload(client, project, content):
    return client.post(
        f"/api/projects/{project}/assets", files={"file": ("batch.csv", content)}
    ).json()["asset"]


def make_template(client, project):
    response = client.post(
        f"/api/projects/{project}/templates",
        json={
            "title": "Approved distance table",
            "profiles": ["csv"],
            "purpose": "semantic",
            "basis": "Test-only confirmed dictionary, not coastal science",
            "rules": [
                {"field": "distance", "concept": "test_distance", "unit": "m", "support": "point"}
            ],
            "declaration": {"source": "test laboratory", "license": "test fixture only"},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_unapproved_template_does_not_auto_map(workspace):
    _, _, client, project = workspace
    template = make_template(client, project)
    asset = upload(client, project, b"id,distance\n01,10\n02,20\n")
    suggestions = client.get(f"/api/assets/{asset['id']}/suggestions").json()
    assert suggestions["applied"] == []
    assert (
        client.post(f"/api/templates/{template['id']}/approve", json={"revision": 1}).status_code
        == 200
    )
    suggestions = client.get(f"/api/assets/{asset['id']}/suggestions").json()
    assert suggestions["applied"][0]["template_revision"] == 1


def test_new_bytes_reuse_knowledge_but_have_new_binding(workspace):
    _, _, client, project = workspace
    template = make_template(client, project)
    client.post(f"/api/templates/{template['id']}/approve", json={"revision": 1})
    first = upload(client, project, b"id,distance\n01,10\n02,20\n")
    second = upload(client, project, b"id,distance\n01,11\n02,21\n")
    assert first["sha256"] != second["sha256"]
    suggestion = client.get(f"/api/assets/{second['id']}/suggestions").json()
    assert suggestion["applied"][0]["unit"] == "m"
    assert suggestion["applied"][0]["asset_id"] == second["id"]
    task = client.post(
        "/api/tasks", json={"project_id": project, "title": "Next batch", "purpose": "temporal"}
    ).json()
    bound = client.post(
        f"/api/tasks/{task['id']}/sources", json={"expected_revision": 1, "assets": [second["id"]]}
    ).json()
    mapping = next(m for m in bound["draft"]["mapping"] if m["field"] == "table/distance")
    assert mapping["unit"] == "m"
    assert mapping["template_id"] == template["id"]
    assert (
        bound["draft"]["options"]["inherited_declarations"][second["id"]]["license"]
        == "test fixture only"
    )


def test_ambiguous_approved_templates_are_not_silently_picked(workspace):
    _, _, client, project = workspace
    a = make_template(client, project)
    client.post(f"/api/templates/{a['id']}/approve", json={"revision": 1})
    b = client.post(
        f"/api/projects/{project}/templates",
        json={
            "title": "Different meaning",
            "profiles": ["csv"],
            "purpose": "semantic",
            "basis": "Different test dictionary",
            "rules": [
                {"field": "distance", "concept": "other_distance", "unit": "km", "support": "point"}
            ],
        },
    ).json()
    client.post(f"/api/templates/{b['id']}/approve", json={"revision": 1})
    asset = upload(client, project, b"id,distance\n01,10\n02,20\n")
    result = client.get(f"/api/assets/{asset['id']}/suggestions").json()
    assert not result["applied"]
    assert result["issues"][0]["code"] == "MAPPING_AMBIGUOUS"


def test_mapping_conflict_preserves_both_file_and_declaration(workspace, tmp_path):
    import numpy as np
    import rasterio
    from rasterio.transform import from_origin

    _, _, client, project = workspace
    p = tmp_path / "native.tif"
    with rasterio.open(
        p,
        "w",
        driver="GTiff",
        width=2,
        height=2,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(110, 20, 0.01, 0.01),
    ) as ds:
        ds.write(np.ones((2, 2), dtype="float32"), 1)
        ds.set_band_unit(1, "s")
    t = client.post(
        f"/api/projects/{project}/templates",
        json={
            "title": "Distance",
            "profiles": ["geotiff"],
            "purpose": "semantic",
            "basis": "Declared distance",
            "rules": [{"field": "band_1", "concept": "distance", "unit": "m", "support": "grid"}],
        },
    ).json()
    client.post(f"/api/templates/{t['id']}/approve", json={"revision": 1})
    asset = upload(client, project, p.read_bytes())
    result = client.get(f"/api/assets/{asset['id']}/suggestions").json()
    assert result["issues"][0]["code"] == "FILE_TEMPLATE_CONFLICT"
    assert result["issues"][0]["file_unit"] == "s"
    assert result["issues"][0]["template_unit"] == "m"


def test_ordinary_upload_applies_approved_knowledge_atomically(workspace):
    _, _, client, project = workspace
    template = make_template(client, project)
    client.post(f"/api/templates/{template['id']}/approve", json={"revision": 1})
    task = client.post(
        "/api/tasks",
        json={"project_id": project, "title": "Automatic first path", "purpose": "cluster"},
    ).json()
    reply = client.post(
        f"/api/projects/{project}/assets",
        files={"file": ("batch.csv", b"id,distance\n01,10\n02,20\n")},
        data={"task_id": task["id"], "expected_revision": "1"},
    )
    assert reply.status_code == 201, reply.text
    binding = next(
        b for b in reply.json()["task"]["draft"]["mapping"] if b["field"] == "table/distance"
    )
    assert binding["template_id"] == template["id"]
    assert binding["unit"] == "m"


def test_semantic_template_scope_does_not_spread_to_unrelated_data(workspace):
    _, _, client, project = workspace
    response = client.post(
        f"/api/projects/{project}/templates",
        json={
            "title": "PRD only",
            "profiles": ["csv"],
            "purpose": "semantic",
            "basis": "Explicit test collection",
            "scope": {"filenames": ["prd-*.csv"]},
            "rules": [
                {
                    "field": "distance",
                    "concept": "distance to river",
                    "unit": "m",
                    "support": "point",
                }
            ],
        },
    )
    assert response.status_code == 201, response.text
    t = response.json()
    client.post(f"/api/templates/{t['id']}/approve", json={"revision": 1})
    other = upload(client, project, b"id,distance\n01,10\n02,20\n")
    assert not client.get(f"/api/assets/{other['id']}/suggestions").json()["applied"]
    prd = client.post(
        f"/api/projects/{project}/assets",
        files={"file": ("prd-next.csv", b"id,distance\n03,12\n04,22\n")},
    ).json()["asset"]
    assert client.get(f"/api/assets/{prd['id']}/suggestions").json()["applied"][0]["unit"] == "m"


def test_compatible_unit_adaptation_is_automatic_and_traceable(workspace, tmp_path):
    import numpy as np
    import rasterio
    from rasterio.transform import from_origin

    _, _, client, project = workspace
    path = tmp_path / "metres.tif"
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=2,
        height=2,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(110, 23, 0.01, 0.01),
    ) as ds:
        ds.write(np.array([[0, 100], [200, 300]], dtype="float32"), 1)
        ds.set_band_unit(1, "m")
    created = client.post(
        f"/api/projects/{project}/templates",
        json={
            "title": "Kilometre method convention",
            "profiles": ["geotiff"],
            "purpose": "semantic",
            "basis": "Explicit engineering dictionary",
            "rules": [{"field": "band_1", "unit": "km", "concept": "distance", "support": "grid"}],
        },
    ).json()
    client.post(f"/api/templates/{created['id']}/approve", json={"revision": 1})
    asset = upload(client, project, path.read_bytes())
    result = client.get(f"/api/assets/{asset['id']}/suggestions").json()
    assert result["issues"] == []
    assert result["applied"][0]["unit"] == "km"
    assert result["adaptations"][0]["scale"] == 0.001
    assert result["adaptations"][0]["offset"] == 0
    assert result["adaptations"][0]["source_unit"] == "m"
    assert (
        client.get(f"/api/assets/{asset['id']}").json()["facts"]["layers"][0]["fields"][0]["unit"]
        == "m"
    )


def test_semantic_edit_creates_new_unapproved_version_and_invalidates_binding(workspace):
    _, _, client, project = workspace
    t = make_template(client, project)
    client.post(f"/api/templates/{t['id']}/approve", json={"revision": 1})
    asset = upload(client, project, b"id,distance\n01,10\n02,20\n03,30\n04,40\n")
    task = client.post(
        "/api/tasks",
        json={"project_id": project, "title": "Saved prior dictionary", "purpose": "cluster"},
    ).json()
    task = client.post(
        f"/api/tasks/{task['id']}/sources", json={"expected_revision": 1, "assets": [asset["id"]]}
    ).json()
    spec = t["spec"]
    spec["rules"][0]["unit"] = "km"
    changed = client.put(f"/api/templates/{t['id']}", json={"expected_revision": 1, "spec": spec})
    assert changed.status_code == 200, changed.text
    assert changed.json()["revision"] == 2
    assert changed.json()["approved"] is False
    check = client.get(f"/api/tasks/{task['id']}/preflight").json()
    assert any(issue["code"] == "TEMPLATE_CHANGED" for issue in check["issues"])
    history = client.get(f"/api/templates/{t['id']}/history").json()
    assert len(history) == 2
    assert history[0]["spec"]["rules"][0]["unit"] == "m"


def test_partial_unit_knowledge_does_not_invent_concept_or_period(workspace):
    _, _, client, project = workspace
    created = client.post(
        f"/api/projects/{project}/templates",
        json={
            "title": "User supplied distance units only",
            "purpose": "semantic",
            "profiles": ["csv"],
            "basis": "User explicitly stated metres; indicator meanings still unknown",
            "rules": [{"field": "distance", "unit": "m"}],
        },
    )
    assert created.status_code == 201, created.text
    template = created.json()
    client.post(f"/api/templates/{template['id']}/approve", json={"revision": 1})
    asset = upload(client, project, b"id,distance\n01,12\n")
    suggestion = client.get(f"/api/assets/{asset['id']}/suggestions").json()
    assert suggestion["applied"][0]["unit"] == "m"
    assert suggestion["applied"][0]["concept"] is None
    assert suggestion["applied"][0]["support"] is None
    assert suggestion["declaration"] == {}
    assert asset["facts"]["observed_period"] is None


def test_source_year_is_hash_scoped_and_declaration_version_is_rechecked(workspace):
    from coastmas_next.reuse import validate_knowledge

    _, store, client, project = workspace
    first = upload(client, project, b"id,distance\n01,12\n")
    second = upload(client, project, b"id,distance\n01,13\n")
    response = client.post(
        f"/api/projects/{project}/templates",
        json={
            "title": "2022 source statement",
            "purpose": "declaration",
            "profiles": ["csv"],
            "basis": "User statement applies to this supplied batch only",
            "scope": {"asset_sha256": [first["sha256"]]},
            "declaration": {
                "observed_year": 2022,
                "source": "open website",
                "use_restriction": "noncommercial",
            },
        },
    )
    assert response.status_code == 201, response.text
    template = response.json()
    client.post(f"/api/templates/{template['id']}/approve", json={"revision": 1})
    suggestion = client.get(f"/api/assets/{first['id']}/suggestions").json()
    assert suggestion["declaration"]["observed_year"] == 2022
    assert suggestion["declaration_references"][0]["template_id"] == template["id"]
    assert client.get(f"/api/assets/{second['id']}/suggestions").json()["declaration"] == {}
    task = client.post(
        "/api/tasks", json={"project_id": project, "title": "Statement", "purpose": "inspect"}
    ).json()
    bound = client.post(
        f"/api/tasks/{task['id']}/sources", json={"expected_revision": 1, "assets": [first["id"]]}
    ).json()
    assert first["facts"]["observed_period"] is None
    actor = client.get("/api/session").json()["id"]
    assert validate_knowledge(store, actor, project, bound["draft"], [first]) == []
    client.post(f"/api/templates/{template['id']}/revoke", json={"revision": 1})
    assert any(
        issue["code"] == "DECLARATION_CHANGED"
        for issue in validate_knowledge(store, actor, project, bound["draft"], [first])
    )
