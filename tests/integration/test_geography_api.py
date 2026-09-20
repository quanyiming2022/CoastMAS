from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.unit.test_geography import entity_payload


def test_entity_versions_spatial_filters_and_permissions(authenticated, engine):
    client, csrf, project, _ = authenticated
    headers = {"X-CSRF-Token": csrf}
    spec = {**entity_payload(), "id": "geo-" + uuid4().hex}
    created = client.post(
        "/api/v1/entities", headers=headers, json={"project_id": project, "spec": spec}
    )
    assert created.status_code == 201, created.text
    url = "/api/v1/entities/" + spec["id"]
    params = {"project_id": project, "west": 116.9, "south": 30.9, "east": 117.1, "north": 31.1}
    found = client.get("/api/v1/entities/spatial", params=params)
    assert found.status_code == 200, found.text
    assert found.json()["features"][0]["id"] == spec["id"]
    assert found.json()["features"][0]["properties"]["management_unit_id"] == "U1"
    assert (
        client.get(
            "/api/v1/entities/spatial", params={**params, "at": "2019-01-01T00:00:00Z"}
        ).json()["features"]
        == []
    )
    assert (
        client.get("/api/v1/entities/spatial", params={**params, "east": 116.8}).status_code == 422
    )
    assert (
        client.get(
            "/api/v1/entities/spatial", params={**params, "project_id": str(uuid4())}
        ).status_code
        == 403
    )
    updated = {
        **spec,
        "version": 2,
        "name": "Revised boundary",
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[118, 32], [118.01, 32], [118.01, 32.01], [118, 32]]],
        },
    }
    result = client.put(url, headers=headers, json={"expected_version": 1, "spec": updated})
    assert result.status_code == 200, result.text
    assert (
        client.put(url, headers=headers, json={"expected_version": 1, "spec": updated}).status_code
        == 409
    )
    assert client.get(url, params={"version": 1}).json()["spec"]["geometry"] == spec["geometry"]
    assert client.get("/api/v1/entities/spatial", params=params).json()["features"] == []
    historical = client.get(
        "/api/v1/entities/spatial", params={**params, "include_history": True}
    ).json()
    assert [feature["properties"]["version"] for feature in historical["features"]] == [1]
    with engine.connect() as connection:
        assert (
            connection.scalar(
                text("SELECT count(*) FROM geographic_entities WHERE resource_id=:id"),
                {"id": spec["id"]},
            )
            == 2
        )
        with pytest.raises(DBAPIError, match="immutable"):
            connection.execute(
                text("UPDATE geographic_entities SET valid_to=now() WHERE resource_id=:id"),
                {"id": spec["id"]},
            )


def test_projected_entity_materializes_without_changing_source(authenticated):
    client, csrf, project, _ = authenticated
    spec = {
        **entity_payload(),
        "id": "geo-" + uuid4().hex,
        "crs": "EPSG:32650",
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [[500000, 3500000], [500100, 3500000], [500100, 3500100], [500000, 3500000]]
            ],
        },
    }
    response = client.post(
        "/api/v1/entities",
        headers={"X-CSRF-Token": csrf},
        json={"project_id": project, "spec": spec},
    )
    assert response.status_code == 201, response.text
    assert response.json()["spec"]["crs"] == "EPSG:32650"
    spatial = client.get(
        "/api/v1/entities/spatial",
        params={"project_id": project, "west": 116, "east": 118, "south": 30, "north": 33},
    )
    assert spatial.status_code == 200, spatial.text
    coordinates = spatial.json()["features"][0]["geometry"]["coordinates"][0]
    assert coordinates[0][0] == pytest.approx(117)
    assert 31 < coordinates[0][1] < 32


def test_entity_write_permissions_and_invalid_geometry_leave_no_revision(engine, actors):
    from pydantic import ValidationError
    from sqlalchemy.orm import Session

    from coastmas.core.errors import CoastMASError
    from coastmas.persistence.resources import create_resource
    from coastmas.persistence.schema import Resource

    owner, viewer, outsider, project = actors
    identifier = "geo-" + uuid4().hex
    spec = {**entity_payload(), "id": identifier}
    for user in (viewer, outsider):
        with Session(engine) as session:
            with pytest.raises(CoastMASError, match="permission"):
                create_resource(
                    session,
                    user_id=user,
                    project_id=project,
                    kind="entity",
                    identifier=identifier,
                    name=spec["name"],
                    spec=spec,
                )
    with pytest.raises(ValidationError):
        with Session(engine) as session, session.begin():
            create_resource(
                session,
                user_id=owner,
                project_id=project,
                kind="entity",
                identifier=identifier,
                name=spec["name"],
                spec={**spec, "crs": "invalid-crs"},
            )
    with Session(engine) as session:
        assert session.get(Resource, identifier) is None
