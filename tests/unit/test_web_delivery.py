"""Frontend document delivery; no database, science, or permission behavior is mocked."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from coastmas.app.production import register_web


@pytest.fixture
def web(tmp_path):
    distribution = tmp_path / "dist"
    distribution.mkdir()
    (distribution / "index.html").write_text("<!doctype html><main>CoastMAS</main>")
    (distribution / "assets").mkdir()
    (distribution / "assets/app.js").write_text("const frontend = true;")
    outside = tmp_path / "outside.txt"
    outside.write_text("not public")
    (distribution / "escape.txt").symlink_to(outside)
    app = FastAPI()
    register_web(app, distribution)
    with TestClient(app) as client:
        yield client, distribution


@pytest.mark.parametrize(
    "path",
    [
        "/data/scene.dem.tif",
        "/models/model.v2",
        "/scenes/aoi.geojson",
        "/workflows/run.v1?scene=a#inputs",
    ],
)
def test_document_refresh_accepts_dotted_resource_identifiers(web, path):
    client, _ = web
    response = client.get(path, headers={"Accept": "text/html"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "CoastMAS" in response.text
    assert response.headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize(
    "path", ["/assets/missing.js", "/api/v1/missing", "/api", "/escape.txt", "/..%2Foutside.txt"]
)
def test_frontend_fallback_never_exposes_private_files_or_hides_missing_api_assets(web, path):
    client, _ = web
    response = client.get(path, headers={"Accept": "text/html"})
    assert response.status_code == 404
    assert "not public" not in response.text
    assert "<main>" not in response.text


def test_asset_requests_and_absent_build_keep_explicit_errors(web):
    client, distribution = web
    assert client.get("/assets/app.js").text == "const frontend = true;"
    assert client.get("/missing.js").status_code == 404
    (distribution / "index.html").unlink()
    assert client.get("/models/item.v1", headers={"Accept": "text/html"}).status_code == 503
