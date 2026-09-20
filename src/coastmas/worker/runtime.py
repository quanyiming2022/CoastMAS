"""Real queue-to-artifact execution with database leases and fenced publication.

Database QUEUED rows are the durable dispatch source. A periodic dispatcher can
redeliver after a broker outage; duplicate messages cannot acquire a live lease.
Artifacts are immutable per attempt, and only a committed ResultBundle makes
one visible to users. Unpublished attempt objects remain recoverable for an
explicit retention sweeper; they are never reported as successful results.
"""

import hashlib
import json
import logging
import threading
from datetime import UTC, datetime
from pathlib import Path

from celery import Celery  # type: ignore[import-untyped]
from pydantic import JsonValue, TypeAdapter
from sqlalchemy import Engine, or_, select
from sqlalchemy.orm import Session

from coastmas.adapters.datasource import StoredDataResolver
from coastmas.adapters.storage import S3ArtifactStore
from coastmas.core.contracts import DataAssetSpec, ModelSpec, RunManifest, SceneSpec, WorkflowSpec
from coastmas.core.errors import CoastMASError, ConstraintError
from coastmas.core.execution import ExecutionRegistry, execute_workflow
from coastmas.persistence.jobs import claim_job, finish_failed_job, heartbeat_job, publish_result
from coastmas.persistence.resources import fingerprint, read_resource, require_permission
from coastmas.persistence.schema import Job, Resource

LOGGER = logging.getLogger(__name__)
JSON_OUTPUT = TypeAdapter(dict[str, JsonValue])


class WorkflowWorker:
    def __init__(
        self,
        engine: Engine,
        registry: ExecutionRegistry,
        store: S3ArtifactStore,
        *,
        work_root: Path,
    ):
        self.engine = engine
        self.registry = registry
        self.store = store
        self.work_root = work_root

    def _verify_manifest(self, session: Session, job: Job, manifest: RunManifest) -> None:
        require_permission(session, job.submitted_by, job.project_id, "write")
        objects: tuple[SceneSpec | WorkflowSpec | ModelSpec | DataAssetSpec, ...] = (
            manifest.scene,
            manifest.workflow,
            *manifest.models,
            *manifest.data_assets,
        )
        for item in objects:
            record = session.scalar(
                select(Resource)
                .where(Resource.id == item.id)
                .execution_options(populate_existing=True)
            )
            if (
                record is None
                or record.project_id != job.project_id
                or not record.enabled
                or record.archived
            ):
                raise ConstraintError("run input is not an active resource in this project")
            revision = read_resource(
                session, user_id=job.submitted_by, identifier=item.id, version=item.version
            )
            if revision.checksum != fingerprint(item.model_dump(mode="json")):
                raise ConstraintError("run input differs from immutable resource version")

    def run(self, job_id: str) -> None:
        with Session(self.engine) as session, session.begin():
            token = claim_job(session, job_id, lease_seconds=60)
        if token is None:
            return
        stop = threading.Event()
        cancellation = threading.Event()
        heartbeat_errors: list[Exception] = []
        progress = [0.0]
        heartbeat_thread: threading.Thread | None = None

        def heartbeat() -> None:
            while not stop.wait(0.5):
                try:
                    with Session(self.engine) as session, session.begin():
                        alive = heartbeat_job(
                            session,
                            job_id,
                            token,
                            lease_seconds=60,
                            progress=min(progress[0], 0.99),
                        )
                    if not alive:
                        cancellation.set()
                        return
                except Exception as exc:
                    heartbeat_errors.append(exc)
                    cancellation.set()
                    return

        try:
            with Session(self.engine) as session:
                job = session.get(Job, job_id)
                if job is None:
                    raise CoastMASError("EXECUTION_ERROR", "claimed job is unavailable")
                manifest = RunManifest.model_validate(job.manifest)
                self._verify_manifest(session, job, manifest)
                project_id = job.project_id
                input_fingerprint = job.fingerprint
            heartbeat_thread = threading.Thread(
                target=heartbeat, name="coastmas-lease", daemon=True
            )
            heartbeat_thread.start()

            def update_progress(value: float) -> None:
                progress[0] = value

            execution = execute_workflow(
                manifest,
                registry=self.registry,
                resolver=StoredDataResolver(self.store),
                work_root=self.work_root,
                cancel=cancellation,
                on_progress=update_progress,
            )
            if heartbeat_errors:
                raise CoastMASError("LEASE_ERROR", "worker could not maintain its database lease")
            payload = JSON_OUTPUT.validate_python(
                {
                    "outputs": execution.outputs,
                    "node_outputs": execution.node_outputs,
                    "executed_nodes": list(execution.executed_nodes),
                    "bindings": [binding.model_dump(mode="json") for binding in execution.bindings],
                    "run_manifest": manifest.model_dump(mode="json"),
                    "input_fingerprint": input_fingerprint,
                    "elapsed_seconds": execution.elapsed_seconds,
                    "llm_calls": 0,
                }
            )
            content = json.dumps(
                payload, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode()
            digest = hashlib.sha256(content).hexdigest()
            artifact = self.store.put(f"{project_id}/{job_id}/{token}/{digest}.json", content)
            with Session(self.engine) as session, session.begin():
                job = session.get(Job, job_id)
                if job is None:
                    raise CoastMASError("EXECUTION_ERROR", "job disappeared before publication")
                self._verify_manifest(session, job, manifest)
                publish_result(
                    session,
                    job_id=job_id,
                    worker_token=token,
                    manifest={
                        "key": artifact.key,
                        "uri": artifact.uri,
                        "bucket": artifact.bucket,
                        "sha256": artifact.sha256,
                        "size": artifact.size,
                        "input_fingerprint": input_fingerprint,
                        "quality_status": "VALIDATED",
                    },
                )
        except Exception as exc:
            # Exception arguments from DB/SDK/plugins can contain credentials or source data.
            # Preserve type and job identity in private logs, expose only stable error codes.
            code = exc.code if isinstance(exc, CoastMASError) else "EXECUTION_ERROR"
            if heartbeat_errors:
                code = "LEASE_ERROR"
            LOGGER.error(
                "job_failed job=%s exception_type=%s code=%s", job_id, type(exc).__name__, code
            )
            with Session(self.engine) as session, session.begin():
                finish_failed_job(
                    session,
                    job_id,
                    token,
                    code=code,
                    message="execution stopped; inspect authorized job diagnostics",
                )
        finally:
            stop.set()
            if heartbeat_thread is not None:
                heartbeat_thread.join(timeout=10)
                if heartbeat_thread.is_alive():
                    raise CoastMASError(
                        "LEASE_ERROR", "heartbeat did not stop within shutdown budget"
                    )

    def pending(self, limit: int = 100) -> list[str]:
        if not 1 <= limit <= 1000:
            raise ValueError("dispatcher batch outside budget")
        with Session(self.engine) as session:
            identifiers = session.scalars(
                select(Job.id)
                .where(
                    or_(
                        Job.status == "QUEUED",
                        (Job.status == "RUNNING") & (Job.lease_until <= datetime.now(UTC)),
                    )
                )
                .order_by(Job.created_at)
                .limit(limit)
            )
            return list(identifiers)


def create_queue(
    worker: WorkflowWorker, *, broker_url: str, queue_name: str = "coastmas"
) -> Celery:
    application = Celery("coastmas", broker=broker_url)
    application.conf.update(
        task_default_queue=queue_name,
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        task_ignore_result=True,
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        broker_connection_retry_on_startup=True,
        broker_transport_options={"visibility_timeout": 120, "global_keyprefix": queue_name + ":"},
        beat_schedule={"recover-pending": {"task": "coastmas.dispatch", "schedule": 5.0}},
    )
    application.task(name="coastmas.execute", shared=False)(worker.run)

    def dispatch() -> None:
        for identifier in worker.pending():
            application.send_task("coastmas.execute", args=[identifier], queue=queue_name)

    application.task(name="coastmas.dispatch", shared=False)(dispatch)
    return application
