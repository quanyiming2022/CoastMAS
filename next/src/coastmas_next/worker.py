"""Durable leased worker. Partial files and lost leases cannot publish results."""

import json
import logging
import os
import shutil
import threading
import time

from sqlalchemy import or_, select, update

from .asset_integrity import verify_asset
from .execution import jobs
from .store import Problem, identifier

logger = logging.getLogger(__name__)


class Worker:
    def __init__(self, store, lease_seconds=60):
        self.store, self.lease_seconds = store, lease_seconds

    def claim(self):
        now, token = time.time(), identifier()
        with self.store.engine.begin() as c:
            # A crashed owner cannot acknowledge cancellation; finish only expired leases.
            c.execute(
                update(jobs)
                .where(
                    jobs.c.cancel_requested.is_(True),
                    or_(
                        jobs.c.status == "queued",
                        (jobs.c.status == "running") & (jobs.c.lease_until < now),
                    ),
                )
                .values(status="cancelled", finished=now, lease_until=0)
            )
            condition = or_(
                jobs.c.status == "queued", (jobs.c.status == "running") & (jobs.c.lease_until < now)
            )
            row = (
                c.execute(
                    select(jobs)
                    .where(condition, jobs.c.cancel_requested.is_(False))
                    .order_by(jobs.c.created)
                    .with_for_update(skip_locked=True)
                    .limit(1)
                )
                .mappings()
                .first()
            )
            if row is None:
                return None
            count = c.execute(
                update(jobs)
                .where(jobs.c.id == row["id"], condition)
                .values(
                    status="running", lease=token, lease_until=now + self.lease_seconds, started=now
                )
            ).rowcount
            return {**dict(row), "lease": token} if count == 1 else None

    def heartbeat(self, job, stop, cancelled):
        while not stop.wait(self.lease_seconds / 3):
            with self.store.engine.begin() as c:
                row = c.execute(
                    select(jobs.c.cancel_requested, jobs.c.lease).where(jobs.c.id == job["id"])
                ).one()
                if row.cancel_requested or row.lease != job["lease"]:
                    cancelled.set()
                    return
                c.execute(
                    update(jobs)
                    .where(
                        jobs.c.id == job["id"],
                        jobs.c.lease == job["lease"],
                        jobs.c.status == "running",
                    )
                    .values(lease_until=time.time() + self.lease_seconds)
                )

    def compute(self, manifest, cancelled, artifact_dir=None):
        with self.store.engine.connect() as connection:
            self.store.permission(connection, manifest["actor"], manifest["project_id"], write=True)
        if manifest["draft"]["purpose"] == "comparison":
            from .comparison_tasks import compute as compare_compute

            return compare_compute(self.store, manifest, cancelled)
        for asset in manifest["assets"]:
            verify_asset(self.store.settings.storage_root, asset, cancelled)
        if manifest["draft"]["purpose"] == "inspect":
            return {
                "datasets": [
                    {"id": a["id"], "sha256": a["sha256"], "facts": a["facts"]}
                    for a in manifest["assets"]
                ]
            }
        if manifest["draft"]["purpose"] == "spatial":
            from .spatial import compute as spatial_compute

            return spatial_compute(self.store.settings, manifest, cancelled, artifact_dir)
        from .reuse import validate_knowledge

        issues = validate_knowledge(
            self.store,
            manifest["actor"],
            manifest["project_id"],
            manifest["draft"],
            manifest["assets"],
        )
        if issues:
            raise Problem(
                422, "KNOWLEDGE_CHANGED", "运行前相关科学定义资格已改变", {"issues": issues}
            )
        if manifest["draft"]["purpose"] in {"cluster", "regression"}:
            from .models import ModelRegistry
            from .models import compute as projection_compute

            ModelRegistry(self.store).require(
                manifest.get("actor", ""),
                manifest.get("project_id", ""),
                manifest["runtime"]["release"]["model_id"],
            )
            return projection_compute(self.store.settings, manifest, cancelled, artifact_dir)
        if manifest["draft"]["purpose"] in {"assessment", "optimization"}:
            from .decisions import compute as decision_compute

            return decision_compute(self.store, manifest, cancelled, artifact_dir)
        from .science import compute

        return compute(self.store.settings, manifest, cancelled)

    def run_once(self):
        job = self.claim()
        if job is None:
            from .batches import BatchIntake
            from .source_snapshots import SourceSnapshots

            return BatchIntake(self.store).run_once() or SourceSnapshots(self.store).run_once()
        stop, cancelled = threading.Event(), threading.Event()
        pulse = threading.Thread(target=self.heartbeat, args=(job, stop, cancelled), daemon=True)
        pulse.start()
        root = self.store.settings.storage_root
        key = f"results/{job['id']}-{job['lease']}.json"
        path = root / key
        temporary = path.with_suffix(".partial")
        artifact_dir = path.with_suffix("")
        try:
            data = self.compute(job["manifest"], cancelled, artifact_dir)
            if job["manifest"]["draft"]["purpose"] == "spatial":
                from .spatial import validate_outputs

                validate_outputs(job["manifest"], data, root)
            if (
                job["manifest"]["draft"]["purpose"] == "assessment"
                and data.get("scope") == "full_grid"
            ):
                from .raster_assessment import validate_outputs as validate_assessment

                validate_assessment(job["manifest"], data, root)
            from .stage_products import prepare_registration, publish

            products = prepare_registration(self.store, job, data)
            result = {
                "manifest": job["manifest"],
                "data": data,
                "states": {
                    **job["manifest"]["states"],
                    "execution_succeeded": True,
                    "business_validated": False,
                },
                "completed_at": time.time(),
            }
            path.parent.mkdir(parents=True, exist_ok=True)
            with temporary.open("w") as stream:
                json.dump(result, stream, ensure_ascii=False, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(path)
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
            with self.store.engine.begin() as c:
                count = c.execute(
                    update(jobs)
                    .where(
                        jobs.c.id == job["id"],
                        jobs.c.lease == job["lease"],
                        jobs.c.status == "running",
                        jobs.c.cancel_requested.is_(False),
                    )
                    .values(status="succeeded", output_key=key, finished=time.time(), lease_until=0)
                ).rowcount
                if count == 1:
                    publish(c, self.store, job, products)
                    from .planning_units import publish as publish_units

                    publish_units(c, self.store, job, data)
                if count != 1:
                    path.unlink(missing_ok=True)
                    if artifact_dir.exists():
                        shutil.rmtree(artifact_dir)
                    c.execute(
                        update(jobs)
                        .where(
                            jobs.c.id == job["id"],
                            jobs.c.lease == job["lease"],
                            jobs.c.cancel_requested.is_(True),
                        )
                        .values(status="cancelled", finished=time.time())
                    )
        except Exception as exc:
            temporary.unlink(missing_ok=True)
            path.unlink(missing_ok=True)
            if artifact_dir.exists():
                shutil.rmtree(artifact_dir)
            logger.exception("Job %s failed", job["id"])
            error = (
                {"code": exc.code, "message": exc.message, "details": exc.details}
                if isinstance(exc, Problem)
                else {"code": "EXECUTION_FAILED", "message": str(exc)[:1000]}
            )
            with self.store.engine.begin() as c:
                c.execute(
                    update(jobs)
                    .where(
                        jobs.c.id == job["id"],
                        jobs.c.lease == job["lease"],
                        jobs.c.status == "running",
                    )
                    .values(
                        status="cancelled" if cancelled.is_set() else "failed",
                        error=error,
                        finished=time.time(),
                        lease_until=0,
                    )
                )
        finally:
            stop.set()
            pulse.join(timeout=2)
        return True
