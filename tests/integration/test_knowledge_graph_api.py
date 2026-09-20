from uuid import uuid4

from sqlalchemy.orm import Session

from coastmas.persistence.resources import create_resource
from tests.factories import asset, model


def test_graph_reads_only_authorized_versions_and_excludes_runtime_configuration(
    authenticated, engine
):
    client, _, project, owner = authenticated
    spec = model(id="graph-" + uuid4().hex, runtime_config={"authorization": "must-not-expose"})
    data = asset(id="graph-data-" + uuid4().hex)
    with Session(engine) as session, session.begin():
        for kind, item in [("model", spec), ("data", data)]:
            create_resource(
                session,
                user_id=owner,
                project_id=project,
                kind=kind,
                identifier=item.id,
                name=item.name,
                spec=item.model_dump(mode="json"),
            )
    response = client.get("/api/v1/knowledge-graph", params={"project_id": project})
    assert response.status_code == 200, response.text
    assert "must-not-expose" not in response.text
    nodes = response.json()["nodes"]
    center = next(node["id"] for node in nodes if node["type"] == "Model")
    neighborhood = client.get(
        "/api/v1/knowledge-graph", params={"project_id": project, "focus": center, "depth": 2}
    )
    assert neighborhood.status_code == 200, neighborhood.text
    assert any(node["type"] == "DataAsset" for node in neighborhood.json()["nodes"])
    assert (
        client.get("/api/v1/knowledge-graph", params={"project_id": str(uuid4())}).status_code
        == 403
    )
    assert (
        client.get(
            "/api/v1/knowledge-graph", params={"project_id": project, "focus": "missing"}
        ).status_code
        == 404
    )
    assert (
        client.get(
            "/api/v1/knowledge-graph", params={"project_id": project, "depth": 5}
        ).status_code
        == 422
    )
