from fastapi import FastAPI
from fastapi.testclient import TestClient

from coastmas.app.readiness import register_readiness


def test_readiness_reports_each_dependency_without_leaking_failures():
    app = FastAPI()

    def broken():
        raise RuntimeError("private-credential-do-not-expose")

    register_readiness(app, {"database": lambda: None, "storage": broken})
    with TestClient(app) as client:
        response = client.get("/health/ready")
        assert response.status_code == 503
        assert response.json() == {
            "status": "unavailable",
            "dependencies": {"database": "ready", "storage": "unavailable"},
        }
        assert "private-credential" not in response.text
        assert client.get("/health/live").status_code == 200


def test_readiness_all_dependencies_are_required():
    app = FastAPI()
    register_readiness(app, {"database": lambda: None, "storage": lambda: None})
    with TestClient(app) as client:
        assert client.get("/health/ready").json()["status"] == "ready"
