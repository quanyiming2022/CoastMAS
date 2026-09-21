import hashlib
from uuid import uuid4

from sqlalchemy.orm import Session

from coastmas.persistence.resources import create_resource
from tests.factories import asset


def test_image_preview_is_versioned_scoped_and_integrity_checked(authenticated, storage, engine):
    client, _, project, owner = authenticated
    client.app.state.artifact_store = storage
    # Real PNG fixture, no remote service involved in authorization testing.
    import base64

    content = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII="
    )
    record = storage.put(f"{project}/imagery/test.png", content)
    identifier = uuid4().hex
    visualization = {
        "uri": record.uri,
        "checksum": hashlib.sha256(content).hexdigest(),
        "size_bytes": len(content),
        "bounds": [119, 37, 119.1, 37.1],
        "label": "Sentinel-2 test",
        "attribution": "Copernicus Sentinel-2",
        "acquired_at": "2025-09-25T03:07:23Z",
    }
    source = asset(
        id=identifier,
        quality={
            "visualization": visualization,
            "earlier_visualization": {**visualization, "acquired_at": "2024-09-01T00:00:00Z"},
        },
    )
    with Session(engine) as session, session.begin():
        create_resource(
            session,
            user_id=owner,
            project_id=project,
            kind="data",
            identifier=identifier,
            name=source.name,
            spec=source.model_dump(mode="json"),
        )
    prefix = f"/api/v1/data-assets/{identifier}"
    response = client.get(prefix + "/imagery?version=1")
    assert response.status_code == 200, response.text
    assert response.json()["bounds"] == visualization["bounds"]
    assert "uri" not in response.json()
    series = client.get(prefix + "/imagery-series?version=1")
    assert series.status_code == 200, series.text
    assert len(series.json()) == 2
    assert series.json()[1]["acquired_at"].startswith("2024-09-01")
    assert client.get(prefix + "/image?version=1&frame=1").content == content
    assert client.get(prefix + "/image?version=1&frame=2").status_code == 404
    image = client.get(prefix + "/image?version=1")
    assert image.status_code == 200, image.text
    assert image.content == content
    assert image.headers["cache-control"] == "no-store"
    # A forged same-bucket reference must still fail the project object guard.
    visualization["uri"] = storage.put("another-project/imagery/test.png", content).uri
    other = asset(id=uuid4().hex, quality={"visualization": visualization})
    with Session(engine) as session, session.begin():
        create_resource(
            session,
            user_id=owner,
            project_id=project,
            kind="data",
            identifier=other.id,
            name=other.name,
            spec=other.model_dump(mode="json"),
        )
    assert client.get(f"/api/v1/data-assets/{other.id}/image?version=1").status_code == 403
    storage.client.put_object(Bucket=storage.bucket, Key=record.key, Body=b"corrupt")
    assert client.get(prefix + "/image?version=1").status_code == 422
    client.cookies.clear()
    assert client.get(prefix + "/image?version=1").status_code == 401
