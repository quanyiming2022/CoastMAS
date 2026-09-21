"""Publish and optionally execute all three real demos against the running API and worker."""

import argparse
import json
import time
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from coastmas.configuration import configuration_value
from coastmas.persistence.schema import AuditLog, Membership, Project, User
from coastmas.real_imagery import seed_real_imagery
from coastmas.runtime_bootstrap import database_engine, object_store

ROOT = Path(__file__).resolve().parents[1]
PROJECT = str(uuid5(NAMESPACE_URL, "https://coastmas.local/real-optical-demonstrations-v2"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    engine, store = database_engine(), object_store()
    email = configuration_value("COASTMAS_ADMIN_EMAIL", "admin@coastmas.local")
    with Session(engine) as session, session.begin():
        user = session.scalar(
            select(User).where(User.email == email, User.active.is_(True), User.is_admin.is_(True))
        )
        if user is None:
            raise ValueError("active configured administrator is required")
        project = session.get(Project, PROJECT)
        if project is None:
            project = Project(id=PROJECT, name="中国典型海岸真实影像演示", owner_id=user.id)
            session.add(project)
            session.flush()
            session.add(Membership(project_id=PROJECT, user_id=user.id, role="ADMIN"))
            session.add(
                AuditLog(
                    id=str(uuid4()),
                    who=user.id,
                    action="CREATE_PROJECT",
                    resource=PROJECT,
                    old_value=None,
                    new_value={"name": project.name},
                )
            )
            session.flush()
        seeded = seed_real_imagery(
            session, user.id, PROJECT, store, ROOT / "artifacts/runtime/real-imagery/collection-1"
        )
    report = {
        "project_id": PROJECT,
        "scope": "real Sentinel-2 optical demonstrations",
        "scenes": {},
    }
    if args.run:
        with httpx.Client(base_url="http://127.0.0.1:58000", timeout=30) as client:
            response = client.post(
                "/api/v1/auth/login",
                json={"email": email, "password": configuration_value("COASTMAS_ADMIN_PASSWORD")},
            )
            response.raise_for_status()
            csrf = response.json()["csrf_token"]
            for key, workflow in seeded.workflows.items():
                scene = seeded.scenes[key]
                body = {"workflow_version": 1, "scene_id": scene.id, "scene_version": 1}
                preflight = client.post(
                    f"/api/v1/workflows/{workflow.id}/validate",
                    json=body,
                    headers={"X-CSRF-Token": csrf},
                )
                preflight.raise_for_status()
                assert preflight.json()["valid"], preflight.json()["issues"]
                submitted = client.post(
                    f"/api/v1/workflows/{workflow.id}/run",
                    json=body,
                    headers={"X-CSRF-Token": csrf, "Idempotency-Key": f"real-optical-v2-{key}"},
                )
                submitted.raise_for_status()
                job_id = submitted.json()["id"]
                deadline = time.monotonic() + 180
                while True:
                    status = client.get(f"/api/v1/jobs/{job_id}")
                    status.raise_for_status()
                    job = status.json()
                    if job["status"] in {"SUCCEEDED", "FAILED", "CANCELLED"}:
                        break
                    if time.monotonic() >= deadline:
                        raise TimeoutError(f"real imagery job not finished: {job_id}")
                    time.sleep(1)
                if job["status"] != "SUCCEEDED":
                    raise RuntimeError(
                        f"real imagery job {job_id}: {job['status']}; {job.get('error')}"
                    )
                results = client.get("/api/v1/results", params={"project_id": PROJECT})
                results.raise_for_status()
                result = next(item for item in results.json() if item["job_id"] == job_id)
                content = client.get(f"/api/v1/results/{result['id']}/content")
                content.raise_for_status()
                payload = content.json()
                summary = payload["outputs"]["optical.summary"]
                assert summary["valid_pixels"] > 0
                assert payload["llm_calls"] == 0
                assert payload["run_manifest"]["scene"]["id"] == scene.id
                assert payload["outputs"]["optical.preview"]["kind"] == "optical_preview"
                report["scenes"][key] = {
                    "scene_id": scene.id,
                    "workflow_id": workflow.id,
                    "job_id": job_id,
                    "result_id": result["id"],
                    "status": job["status"],
                    "llm_calls": payload["llm_calls"],
                    "summary": summary,
                }
    path = ROOT / "artifacts/runtime/real-imagery/demo-report.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    print(
        json.dumps(
            {
                "project_id": PROJECT,
                "scenes": len(seeded.scenes),
                "executed": len(report["scenes"]),
                "report": str(path.relative_to(ROOT)),
            }
        )
    )


if __name__ == "__main__":
    main()
