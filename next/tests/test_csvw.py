"""CSVW companion metadata must affect actual rows, identity and method inputs."""

import io
import json
import zipfile

import pytest
from coastmas_next.observations import read_rows
from coastmas_next.worker import Worker


def package(metadata=None, content="ID;Length;Valid\n001;1,25;true\n002;NA;false\n"):
    meta = metadata or {
        "@context": "http://www.w3.org/ns/csvw",
        "url": "data.csv",
        "dialect": {"delimiter": ";", "encoding": "utf-8"},
        "tableSchema": {
            "primaryKey": "id",
            "columns": [
                {"name": "id", "titles": "ID", "datatype": "string", "required": True},
                {
                    "name": "length",
                    "titles": "Length",
                    "null": "NA",
                    "datatype": {"base": "double", "format": {"decimalChar": ","}},
                },
                {"name": "valid", "titles": "Valid", "datatype": "boolean"},
            ],
        },
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("data.csv", content)
        archive.writestr("data.csv-metadata.json", json.dumps(meta))
    return output.getvalue()


def upload(client, project, payload):
    return client.post(f"/api/projects/{project}/assets", files={"file": ("standard.zip", payload)})


def test_csvw_reads_types_null_decimal_comma_and_leading_zero_identity(workspace):
    settings, store, client, project = workspace
    original = package()
    reply = upload(client, project, original)
    assert reply.status_code == 201, reply.text
    asset = reply.json()["asset"]
    assert asset["facts"]["profile"] == "csvw"
    assert asset["facts"]["standard_version"] == "W3C-REC-2015-12-17"
    assert asset["facts"]["layers"][0]["preview"] == [
        {"id": "001", "length": 1.25, "valid": True},
        {"id": "002", "length": None, "valid": False},
    ]
    task = client.post(
        "/api/tasks",
        json={"project_id": project, "title": "CSVW actual rows", "purpose": "inspect"},
    ).json()
    task = client.post(
        f"/api/tasks/{task['id']}/sources", json={"expected_revision": 1, "assets": [asset["id"]]}
    ).json()
    assert task["draft"]["mapping"][0]["role"] == "identity"
    manifest = {"assets": [store_asset(store, asset["id"])], "draft": task["draft"]}
    rows, _ = read_rows(settings, manifest)
    assert [r["id"] for r in rows] == ["001", "002"]
    assert rows[0]["properties"]["length"] == 1.25
    assert rows[1]["properties"]["length"] is None
    run = client.post(
        f"/api/tasks/{task['id']}/execute",
        json={"expected_revision": task["revision"], "idempotency_key": "csvw"},
    ).json()
    assert Worker(store).run_once()
    result = client.get(f"/api/jobs/{run['id']}/result").json()
    assert result["data"]["datasets"][0]["facts"]["layers"][0]["row_count"] == 2
    assert client.get(f"/api/assets/{asset['id']}/download").content == original


def store_asset(store, asset_id):
    from coastmas_next.intake import assets
    from sqlalchemy import select

    with store.engine.connect() as connection:
        return dict(
            connection.execute(select(assets).where(assets.c.id == asset_id)).mappings().one()
        )


@pytest.mark.parametrize(
    "content,code",
    [
        ("ID;Length;Valid\n001;1,25;true\n001;2,5;false\n", "CSVW_PRIMARY_KEY"),
        ("ID;Length;Valid\n001;wrong;true\n", "CSVW_VALUE"),
        ("ID;Length;Valid\n001;2,5\n", "CSVW_ROW_WIDTH"),
    ],
)
def test_csvw_does_not_silently_coerce_or_drop_invalid_rows(workspace, content, code):
    _, _, client, project = workspace
    response = upload(client, project, package(content=content))
    assert response.status_code == 422, response.text
    assert response.json()["code"] == code


def test_csvw_never_fetches_external_or_traversal_table_references(workspace):
    _, _, client, project = workspace
    for url in ["http://127.0.0.1/private.csv", "../secret.csv", "/etc/passwd"]:
        response = upload(
            client,
            project,
            package(
                {
                    "@context": "http://www.w3.org/ns/csvw",
                    "url": url,
                    "tableSchema": {"columns": [{"name": "id"}]},
                }
            ),
        )
        assert response.status_code == 422
        assert response.json()["code"] == "CSVW_REFERENCE"


def test_csvw_actual_assessment_and_export_roundtrip(workspace):
    settings, store, client, project = workspace
    asset = upload(
        client, project, package(content="ID;Length;Valid\n001;1,25;true\n002;2,5;false\n")
    ).json()["asset"]
    task = client.post(
        "/api/tasks",
        json={"project_id": project, "title": "CSVW method execution", "purpose": "assessment"},
    ).json()
    task = client.post(
        f"/api/tasks/{task['id']}/sources", json={"expected_revision": 1, "assets": [asset["id"]]}
    ).json()
    method = client.post(
        f"/api/projects/{project}/templates",
        json={
            "title": "Explicit engineering bounds",
            "purpose": "method",
            "profiles": ["csvw"],
            "basis": "Engineering fixture, no coastal conclusion",
            "configuration": {
                "task": "assessment",
                "method": "weighted",
                "indicators": [
                    {
                        "concept": "length",
                        "unit": "m",
                        "lower": 0,
                        "upper": 5,
                        "positive": True,
                        "weight": 1,
                    }
                ],
            },
        },
    ).json()
    assert (
        client.post(f"/api/templates/{method['id']}/approve", json={"revision": 1}).status_code
        == 200
    )
    task["draft"]["mapping"][1].update(concept="length", unit="m", support="point")
    task["draft"]["method_id"] = method["id"]
    task["draft"]["options"]["method_revision"] = 1
    task = client.put(
        f"/api/tasks/{task['id']}",
        json={"expected_revision": task["revision"], "draft": task["draft"]},
    ).json()
    run = client.post(
        f"/api/tasks/{task['id']}/execute",
        json={"expected_revision": task["revision"], "idempotency_key": "csvw-calc"},
    )
    assert run.status_code == 202, run.text
    assert Worker(store).run_once()
    result = client.get(f"/api/jobs/{run.json()['id']}/result").json()
    assert result["data"]["row_ids"] == ["001", "002"]
    assert result["data"]["scores"] == [0.25, 0.5]
    output = client.get(f"/api/jobs/{run.json()['id']}/bundle")
    assert output.status_code == 200
    roundtrip = upload(client, project, output.content)
    assert roundtrip.status_code == 201, roundtrip.text
    returned = roundtrip.json()["asset"]["facts"]["layers"][0]["preview"]
    assert [r["row_id"] for r in returned] == ["001", "002"]
    assert [r["scores"] for r in returned] == [0.25, 0.5]


def test_csvw_unimplemented_semantics_preserve_registration_but_block_computation(workspace):
    settings, store, client, project = workspace
    meta = {
        "@context": "http://www.w3.org/ns/csvw",
        "url": "data.csv",
        "tableSchema": {"columns": [{"name": "value", "datatype": "date"}]},
    }
    response = upload(client, project, package(meta, "value\n2022-01-01\n"))
    assert response.status_code == 201, response.text
    asset = response.json()["asset"]
    assert asset["facts"]["layers"][0]["row_count"] is None
    assert asset["facts"]["issues"][0]["code"] == "CSVW_SEMANTICS_UNSUPPORTED"
    from coastmas_next.store import Problem

    with pytest.raises(Problem) as caught:
        read_rows(
            settings,
            {
                "assets": [store_asset(store, asset["id"])],
                "draft": {"selection": [{"asset_id": asset["id"], "layer": None}], "mapping": []},
            },
        )
    assert caught.value.code == "CSVW_SEMANTICS_UNSUPPORTED"


@pytest.mark.parametrize("lexical", ["1_000", "1.2.3", "NaN", "Infinity"])
def test_csvw_numeric_lexical_errors_never_coerce(workspace, lexical):
    _, _, client, project = workspace
    response = upload(client, project, package(content=f"ID;Length;Valid\n001;{lexical};true\n"))
    assert response.status_code == 422
    assert response.json()["code"] == "CSVW_VALUE"


def test_csvw_nested_multitable_selection_has_local_identity(workspace):
    settings, store, client, project = workspace
    buffer = io.BytesIO()
    meta = {
        "@context": "http://www.w3.org/ns/csvw",
        "tables": [
            {
                "url": name,
                "tableSchema": {
                    "primaryKey": "id",
                    "columns": [{"name": "id"}, {"name": "score", "datatype": "double"}],
                },
            }
            for name in ["tables/a.csv", "tables/b.csv"]
        ],
    }
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("metadata.json", json.dumps(meta))
        archive.writestr("tables/a.csv", "id,score\n001,0\n")
        archive.writestr("tables/b.csv", "id,score\n001,5\n")
    response = upload(client, project, buffer.getvalue())
    assert response.status_code == 201, response.text
    asset = response.json()["asset"]
    task = client.post(
        "/api/tasks",
        json={"project_id": project, "title": "Select CSVW table", "purpose": "inspect"},
    ).json()
    task = client.post(
        f"/api/tasks/{task['id']}/sources", json={"expected_revision": 1, "assets": [asset["id"]]}
    ).json()
    manifest = {"assets": [store_asset(store, asset["id"])], "draft": task["draft"]}
    from coastmas_next.store import Problem

    with pytest.raises(Problem) as caught:
        read_rows(settings, manifest)
    assert caught.value.code == "LAYER_REQUIRED"
    manifest["draft"]["selection"][0]["layer"] = "tables/b.csv"
    rows, _ = read_rows(settings, manifest)
    assert rows[0]["id"] == "001"
    assert rows[0]["properties"]["score"] == 5


@pytest.mark.parametrize(
    "columns",
    [
        ["not-an-object"],
        [{"name": "x", "datatype": None}],
        [{"name": "x", "datatype": {"base": []}}],
    ],
)
def test_malformed_csvw_metadata_returns_user_error_not_server_error(workspace, columns):
    _, _, client, project = workspace
    meta = {
        "@context": "http://www.w3.org/ns/csvw",
        "url": "data.csv",
        "tableSchema": {"columns": columns},
    }
    response = upload(client, project, package(meta, "x\n1\n"))
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "CSVW_SCHEMA"
