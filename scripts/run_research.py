"""Run a fixed planning comparison via the live API/worker and retain actual evidence.

Synthetic scientific fixtures stay in the already archived validation project;
this does not add test scenes or records to the visible real-imagery workspace.
"""

import argparse
import json
import time
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from coastmas.configuration import configuration_value
from coastmas.core.research_provider import provider_identity
from coastmas.persistence.schema import Project, ProviderRequest, User
from coastmas.runtime_bootstrap import (
    DEFAULT_PROJECT_ID,
    configured_provider,
    database_engine,
    object_store,
    sample_directory,
)
from coastmas.sample_bootstrap import seed_project

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", action="store_true")
    parser.add_argument("--origin", choices=["LOCAL", "EXTERNAL"], default="LOCAL")
    parser.add_argument("--key", required=True)
    args = parser.parse_args()
    if args.provider:
        provider = configured_provider()
        if provider is None or provider_identity(provider).origin != args.origin:
            raise ValueError("configured provider does not match the explicitly selected origin")
    engine = database_engine()
    email = configuration_value("COASTMAS_ADMIN_EMAIL", "admin@coastmas.local")
    with Session(engine) as session, session.begin():
        user = session.scalar(
            select(User).where(User.email == email, User.active.is_(True), User.is_admin.is_(True))
        )
        project = session.get(Project, DEFAULT_PROJECT_ID)
        if user is None or project is None or not project.archived:
            raise ValueError("requires configured administrator and archived validation project")
        seeded = seed_project(session, user.id, project.id, object_store(), sample_directory())
    workflow, scene = seeded.workflows["B"], seeded.scenes["B"]
    models = sorted({(node.model_id, node.model_version) for node in workflow.nodes})
    assets = sorted(
        {(binding.source.id, binding.source.version) for binding in workflow.input_bindings}
    )
    body = {
        "project_id": DEFAULT_PROJECT_ID,
        "cases": [
            {
                "id": "synthetic-equal-weight-assessment",
                "goal": "可持续性评价：等权综合评价",
                "scene": {"id": scene.id, "version": scene.version},
                "models": [{"id": i, "version": v} for i, v in models],
                "assets": [{"id": i, "version": v} for i, v in assets],
            }
        ],
        "experiments": ["A", "B", "C"],
        "repetitions": 1,
        "allow_provider": args.provider,
    }
    with httpx.Client(base_url="http://127.0.0.1:58000", timeout=30) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": configuration_value("COASTMAS_ADMIN_PASSWORD")},
        )
        login.raise_for_status()
        submitted = client.post(
            "/api/v1/research",
            json=body,
            headers={"X-CSRF-Token": login.json()["csrf_token"], "Idempotency-Key": args.key},
        )
        submitted.raise_for_status()
        job_id = submitted.json()["id"]
        deadline = time.monotonic() + 330
        while True:
            response = client.get("/api/v1/jobs/" + job_id)
            response.raise_for_status()
            job = response.json()
            if job["status"] in {"SUCCEEDED", "FAILED", "CANCELLED"}:
                break
            if time.monotonic() > deadline:
                raise TimeoutError("research still running: " + job_id)
            time.sleep(1)
        if job["status"] != "SUCCEEDED":
            raise RuntimeError(f"research job {job_id}: {job['status']}; {job['error']}")
        response = client.get("/api/v1/research/" + job_id + "/report")
        response.raise_for_status()
        content = response.json()
    ledger = []
    with Session(engine) as session:
        for trial in content["report"]["trials"]:
            if not trial["trace_id"]:
                continue
            records = session.scalars(
                select(ProviderRequest)
                .where(ProviderRequest.trace_id == trial["trace_id"])
                .order_by(ProviderRequest.ordinal)
            )
            for record in records:
                ledger.append(
                    {
                        "id": record.id,
                        "trace_id": record.trace_id,
                        "status": record.status,
                        "provider_model": record.provider_model,
                        "response_model": record.response_model,
                        "dispatched_at": record.dispatched_at.isoformat()
                        if record.dispatched_at
                        else None,
                        "finished_at": record.finished_at.isoformat()
                        if record.finished_at
                        else None,
                        "request_fingerprint": record.request_fingerprint,
                        "response_fingerprint": record.response_fingerprint,
                        "usage": record.usage,
                        "error_code": record.error_code,
                        "http_status": record.http_status,
                    }
                )
    report = {
        "job_id": job_id,
        "dataset_origin": "SYNTHETIC fixed scientific fixture",
        "provider_origin": args.origin if args.provider else "NOT_CONFIGURED",
        "evidence": content,
        "provider_ledger": ledger,
    }
    output = ROOT / "artifacts/research" / ("planning-" + job_id + ".json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "report": str(output.relative_to(ROOT)),
                "job_id": job_id,
                "evaluation_status": content["report"]["status"],
                "metrics": content["report"]["metrics"],
            },
            ensure_ascii=False,
        )
    )
    if args.provider:
        assert content["research_manifest"]["provider"]["origin"] == args.origin
        assert len(ledger) == 2 and sum(row["dispatched_at"] is not None for row in ledger) == 2
        assert content["provider_requests"] == 2
        assert content["report"]["status"] == "COMPLETE", (
            "provider trials did not complete; inspect preserved report"
        )
    engine.dispose()


if __name__ == "__main__":
    main()
