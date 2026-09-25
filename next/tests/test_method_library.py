"""Method maintenance persists separately from research and exports fixed science."""

import io
import json


def definition(title="方法甲"):
    return {
        "title": title,
        "purpose": "method",
        "basis": "明确工程试验，非真实海岸评价结论",
        "profiles": ["csv", "geotiff"],
        "configuration": {
            "task": "assessment",
            "method": "weighted",
            "indicators": [
                {
                    "concept": "quality",
                    "unit": "1",
                    "lower": 0.0,
                    "upper": 1.0,
                    "positive": True,
                    "weight": 1.0,
                }
            ],
        },
    }


def create(client, project, value=None):
    reply = client.post(
        f"/api/projects/{project}/method-workspaces", json={"definition": value or definition()}
    )
    assert reply.status_code == 201, reply.text
    return reply.json()


def publish(client, editor):
    reply = client.post(
        f"/api/method-workspaces/{editor['id']}/publish",
        json={"expected_revision": editor["revision"], "approve": True},
    )
    assert reply.status_code == 201, reply.text
    return reply.json()


def test_durable_method_editor_fixed_publication_clone_and_roundtrip(workspace):
    _, _, client, project = workspace
    before = client.get(f"/api/management/catalog/tasks?project={project}").json()["total"]
    editor = create(client, project)
    changed = definition("修订标题")
    editor = client.put(
        f"/api/method-workspaces/{editor['id']}",
        json={"expected_revision": 1, "definition": changed},
    ).json()
    assert editor["revision"] == 2
    conflict = client.put(
        f"/api/method-workspaces/{editor['id']}",
        json={"expected_revision": 1, "definition": definition()},
    )
    assert conflict.status_code == 409
    assert (
        client.get(f"/api/method-workspaces/{editor['id']}").json()["definition"]["title"]
        == "修订标题"
    )
    first = publish(client, editor)
    assert publish(client, editor)["template"]["id"] == first["template"]["id"]
    mid = first["template"]["id"]
    task = client.post(
        "/api/tasks",
        json={"project_id": project, "goal": "comprehensive-assessment", "title": "研究"},
    ).json()
    applied = client.post(
        f"/api/tasks/{task['id']}/apply-method",
        json={"expected_revision": 1, "method_id": mid, "method_revision": 1},
    )
    assert applied.status_code == 200, applied.text
    opened = client.post(f"/api/methods/{mid}/edit", json={"revision": 1, "mode": "revise"}).json()
    changed["configuration"]["indicators"][0]["upper"] = 2.0
    opened = client.put(
        f"/api/method-workspaces/{opened['id']}",
        json={"expected_revision": opened["revision"], "definition": changed},
    ).json()
    second = publish(client, opened)
    assert second["template"]["revision"] == 2
    historical = client.get(f"/api/methods/{mid}/versions/1")
    assert historical.status_code == 200
    assert historical.json()["spec"]["configuration"]["indicators"][0]["upper"] == 1.0
    assert client.get(f"/api/tasks/{task['id']}").json()["draft"]["options"]["method_revision"] == 1
    again = client.post(
        f"/api/tasks/{task['id']}/apply-method",
        json={"expected_revision": 2, "method_id": mid, "method_revision": 1},
    )
    assert again.status_code == 200, again.text
    for format in ["json", "yaml"]:
        exported = client.get(f"/api/methods/{mid}/versions/1/export?format={format}")
        assert exported.status_code == 200
        imported = client.post(
            f"/api/projects/{project}/method-imports",
            files={"file": ("method." + format, exported.content)},
        )
        assert imported.status_code == 201, imported.text
        clone = publish(client, imported.json())["template"]
        assert clone["id"] != mid and clone["revision"] == 1
        assert clone["spec"]["configuration"]["indicators"][0]["upper"] == 1.0
    cloned = client.post(f"/api/methods/{mid}/edit", json={"revision": 1, "mode": "clone"}).json()
    assert publish(client, cloned)["template"]["id"] != mid
    assert (
        client.get(f"/api/management/catalog/tasks?project={project}").json()["total"] == before + 1
    )


def test_table_import_preserves_missing_science_and_rejects_bad_definition(workspace):
    _, _, client, project = workspace
    content = "指标,单位,下限,上限,方向,权重\n质量,1,0,1,正向,0.4\n压力,1,0,10,负向,0.6\n".encode()
    reply = client.post(
        f"/api/projects/{project}/method-imports", files={"file": ("方案.csv", content)}
    )
    assert reply.status_code == 201, reply.text
    editor = reply.json()
    assert editor["definition"]["basis"] == ""
    assert editor["definition"]["configuration"]["indicators"][1]["positive"] is False
    assert (
        client.post(
            f"/api/method-workspaces/{editor['id']}/publish",
            json={"expected_revision": 1, "approve": True},
        ).status_code
        == 422
    )
    wrong = definition()
    wrong["configuration"]["indicators"][0]["weight"] = 0.4
    bad = create(client, project, wrong)
    response = client.post(
        f"/api/method-workspaces/{bad['id']}/publish",
        json={"expected_revision": 1, "approve": True},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "METHOD_DEFINITION"
    evil = client.post(
        f"/api/projects/{project}/method-imports",
        files={"file": ("bad.yaml", b'!!python/object/apply:os.system ["touch /tmp/invalid"]')},
    )
    assert evil.status_code == 422
    novel = client.post(
        f"/api/projects/{project}/method-imports",
        files={
            "file": (
                "v9.json",
                json.dumps(
                    {"format": "coastmas.method", "version": "9.0", "definition": definition()}
                ).encode(),
            )
        },
    )
    assert novel.status_code == 422 and novel.json()["code"] == "METHOD_STANDARD_VERSION"
    from openpyxl import Workbook

    book = Workbook()
    sheet = book.active
    sheet.append(["指标", "单位", "下限", "上限", "方向", "权重"])
    sheet.append(["质量", "1", 0, 1, "正向", 1])
    stream = io.BytesIO()
    book.save(stream)
    excel = client.post(
        f"/api/projects/{project}/method-imports", files={"file": ("方案.xlsx", stream.getvalue())}
    )
    assert excel.status_code == 201, excel.text
    assert excel.json()["definition"]["configuration"]["indicators"][0]["weight"] == 1


def test_method_permissions_and_project_lifecycle(workspace):
    _, _, client, project = workspace
    editor = create(client, project)
    login = client.post(
        "/api/session", json={"email": "viewer@example.test", "password": "safe-password-for-tests"}
    ).json()
    client.headers["X-CSRF-Token"] = login["csrf"]
    assert client.get(f"/api/method-workspaces/{editor['id']}").status_code == 200
    assert (
        client.put(
            f"/api/method-workspaces/{editor['id']}",
            json={"expected_revision": 1, "definition": definition()},
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/method-workspaces/{editor['id']}/publish",
            json={"expected_revision": 1, "approve": True},
        ).status_code
        == 403
    )


def test_revoked_method_cannot_regain_approval_when_it_becomes_historical(workspace):
    _, _, client, project = workspace
    original = publish(client, create(client, project))["template"]
    mid = original["id"]
    task = client.post(
        "/api/tasks",
        json={"project_id": project, "goal": "comprehensive-assessment", "title": "撤销版本试验"},
    ).json()
    revoked = client.post(f"/api/templates/{mid}/revoke", json={"revision": 1})
    assert revoked.status_code == 200, revoked.text
    edit = client.post(f"/api/methods/{mid}/edit", json={"revision": 1, "mode": "revise"}).json()
    assert publish(client, edit)["template"]["revision"] == 2
    historical = client.get(f"/api/methods/{mid}/versions/1").json()
    assert historical["approved"] is False
    assert historical["approved_by"] is None
    reply = client.post(
        f"/api/tasks/{task['id']}/apply-method",
        json={"expected_revision": 1, "method_id": mid, "method_revision": 1},
    )
    assert reply.status_code == 422 and reply.json()["code"] == "METHOD_CHANGED"
    assert client.get(f"/api/tasks/{task['id']}").json()["revision"] == 1


def test_partial_draft_types_and_publish_business_errors(workspace):
    _, _, client, project = workspace
    value = definition()
    value["basis"] = ""
    value["configuration"]["indicators"] = []
    draft = create(client, project, value)
    saved = client.put(
        f"/api/method-workspaces/{draft['id']}", json={"expected_revision": 1, "definition": value}
    )
    assert saved.status_code == 200
    publish_reply = client.post(
        f"/api/method-workspaces/{draft['id']}/publish", json={"expected_revision": 2}
    )
    assert publish_reply.status_code == 422
    assert "TemplateSpec" not in publish_reply.text and "input_value" not in publish_reply.text
    assert publish_reply.json()["details"]["issues"][0]["field"] == "basis"
    assert client.get(f"/api/method-workspaces/{draft['id']}").json()["publication"] is None
    invalid = definition()
    invalid["basis"] = {"wrong": "type"}
    assert (
        client.put(
            f"/api/method-workspaces/{draft['id']}",
            json={"expected_revision": 2, "definition": invalid},
        ).status_code
        == 422
    )
    invalid = definition()
    invalid["configuration"]["indicators"][0]["positive"] = "false"
    assert (
        client.put(
            f"/api/method-workspaces/{draft['id']}",
            json={"expected_revision": 2, "definition": invalid},
        ).status_code
        == 422
    )
    assert client.get(f"/api/method-workspaces/{draft['id']}").json()["revision"] == 2


def test_partial_indicator_import_retains_original_without_inventing_science(workspace):
    _, _, client, project = workspace
    content = "指标,单位\nNDVI,1\n".encode()
    response = client.post(
        f"/api/projects/{project}/method-imports", files={"file": ("部分指标.csv", content)}
    )
    assert response.status_code == 201, response.text
    draft = response.json()
    row = draft["definition"]["configuration"]["indicators"][0]
    assert row["lower"] is None and row["weight"] is None and row["positive"] is None
    source = client.get(f"/api/method-workspaces/{draft['id']}/source")
    assert source.status_code == 200 and source.content == content


def test_incomplete_optimization_and_ahp_drafts_keep_strict_types(workspace):
    _, _, client, project = workspace
    for configuration in [
        {"task": "optimization", "method": "binary_allocation", "budget": {"value": 1}},
        {
            "task": "assessment",
            "method": "weighted",
            "weighting": {"method": "ahp", "labels": ["x"], "matrix": [["false"]]},
        },
        {"task": "assessment", "method": "weighted", "unknown_scientific_parameter": 2},
    ]:
        response = client.post(
            f"/api/projects/{project}/method-workspaces",
            json={"definition": {**definition(), "configuration": configuration}},
        )
        assert response.status_code == 422, response.text
        assert response.json()["code"] == "METHOD_DRAFT_STRUCTURE"


def test_indicator_table_import_appends_to_existing_draft_and_retains_source(workspace):
    _, _, client, project = workspace
    draft = create(client, project)
    raw = "指标,单位\n温度,kelvin\n".encode()
    imported = client.post(
        f"/api/method-workspaces/{draft['id']}/indicators:import",
        files={"file": ("partial.csv", raw)},
        data={"expected_revision": 1},
    )
    assert imported.status_code == 200, imported.text
    row = imported.json()
    assert row["id"] == draft["id"] and row["revision"] == 2
    indicators = row["definition"]["configuration"]["indicators"]
    assert len(indicators) == 2 and indicators[1]["lower"] is None
    assert row["publication"] is None
    assert client.get(f"/api/method-workspaces/{draft['id']}/sources/0").content == raw
    assert client.get(f"/api/projects/{project}/assets").json() == []
    conflict = client.post(
        f"/api/method-workspaces/{draft['id']}/indicators:import",
        files={"file": ("partial.csv", raw)},
        data={"expected_revision": 1},
    )
    assert conflict.status_code == 409
