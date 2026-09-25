"""New task API commits a complete real original-model raster and authorized download."""

import hashlib
import json
from pathlib import Path

import numpy as np
import rasterio
from coastmas_next.app import create_app
from coastmas_next.config import Settings
from coastmas_next.store import Store
from coastmas_next.worker import Worker
from fastapi.testclient import TestClient
from rasterio.transform import from_origin

ROOT = Path(__file__).resolve().parents[1]


def test_raster_task_executes_and_downloads_complete_geotiff(tmp_path):
    catalog = json.loads((ROOT / ".state/verified-runtimes.json").read_text())
    for release in catalog:
        release["runner_sha256"] = hashlib.sha256(
            (ROOT / "runtime/stream.R").read_bytes()
        ).hexdigest()
        release["application_proof_sha256"] = hashlib.sha256(
            (ROOT / "artifacts/small-full-domain-proof.json").read_bytes()
        ).hexdigest()
    runtime = tmp_path / "runtimes.json"
    runtime.write_text(json.dumps(catalog))
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/new.db",
        storage_root=tmp_path / "objects",
        runtime_catalog=runtime,
    )
    store = Store(settings)
    store.initialize()
    actor = store.create_account("test@example.test", "isolated-science-test")
    project = store.create_project(actor, "Full raster test")
    client = TestClient(create_app(settings))
    login = client.post(
        "/api/session", json={"email": "test@example.test", "password": "isolated-science-test"}
    ).json()
    client.headers["X-CSRF-Token"] = login["csrf"]
    task = client.post(
        "/api/tasks",
        json={
            "project_id": project,
            "title": "Original clustering full raster",
            "purpose": "cluster",
        },
    ).json()
    rng = np.random.default_rng(22)
    for i in range(2):
        path = tmp_path / f"input{i}.tif"
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            width=12,
            height=12,
            count=1,
            dtype="float64",
            crs="EPSG:4326",
            transform=from_origin(110, 23, 0.01, 0.01),
        ) as ds:
            ds.write(rng.normal(size=(12, 12)), 1)
            ds.set_band_unit(1, "m")
        with path.open("rb") as source:
            uploaded = client.post(
                f"/api/projects/{project}/assets",
                files={"file": (path.name, source)},
                data={"task_id": task["id"], "expected_revision": str(task["revision"])},
            )
        assert uploaded.status_code == 201, uploaded.text
        task = uploaded.json()["task"]
    for i, binding in enumerate(task["draft"]["mapping"]):
        binding.update(concept=f"explicit engineering variable {i}", support="grid")
    task["draft"]["options"].update(
        standardize=False, size=2, seed=42, training_scope="all", application_scope="full"
    )
    task = client.put(
        f"/api/tasks/{task['id']}",
        json={"expected_revision": task["revision"], "draft": task["draft"]},
    ).json()
    release = next(
        r
        for r in client.get(f"/api/projects/{project}/models").json()
        if r["release"]["model_id"] == "ppci_mcdc"
    )
    assert (
        client.post(
            f"/api/projects/{project}/models/ppci_mcdc/approve",
            json={"release_digest": release["release_digest"]},
        ).status_code
        == 200
    )
    job = client.post(
        f"/api/tasks/{task['id']}/execute",
        json={"expected_revision": task["revision"], "idempotency_key": "full"},
    )
    assert job.status_code == 202, job.text
    job = job.json()
    assert Worker(store).run_once()
    status = client.get(f"/api/jobs/{job['id']}").json()
    assert status["status"] == "succeeded", status
    result = client.get(f"/api/jobs/{job['id']}/result").json()
    assert result["data"]["application"]["predicted_cells"] == 144
    assert result["data"]["trained_model"]["fit_count"] == 1
    download = client.get(f"/api/jobs/{job['id']}/files/0")
    assert download.status_code == 200, download.text
    assert hashlib.sha256(download.content).hexdigest() == result["data"]["files"][0]["sha256"]
    with rasterio.io.MemoryFile(download.content) as mem:
        with mem.open() as ds:
            assert ds.shape == (12, 12)
            assert set(np.unique(ds.read(1))) == {1, 2}
    assert TestClient(create_app(settings)).get(f"/api/jobs/{job['id']}/files/0").status_code == 401
