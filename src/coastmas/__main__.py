"""python -m coastmas {init,api,worker,beat}; all paths are explicit and project-local."""

import argparse
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.orm import Session

from coastmas.configuration import configuration_value
from coastmas.runtime_bootstrap import (
    DEFAULT_PROJECT_ID,
    BuiltinRuntimeRegistry,
    database_engine,
    initialize_account,
    object_store,
    project_root,
    sample_directory,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="CoastMAS application services")
    parser.add_argument("service", choices=["init", "api", "worker", "beat"])
    args = parser.parse_args()
    if args.service == "init":
        from coastmas.sample_bootstrap import seed_project

        engine = database_engine()
        migration = Config(str(project_root() / "alembic.ini"))
        migration.set_main_option("script_location", str(project_root() / "migrations"))
        migration.attributes["engine"] = engine
        command.upgrade(migration, "head")
        store = object_store()
        store.ensure_bucket()
        with Session(engine) as session, session.begin():
            owner, project = initialize_account(
                session,
                configuration_value("COASTMAS_ADMIN_EMAIL", "admin@coastmas.local"),
                configuration_value("COASTMAS_ADMIN_PASSWORD"),
                configuration_value("COASTMAS_PROJECT_ID", DEFAULT_PROJECT_ID),
            )
            seeded = seed_project(session, owner, project, store, sample_directory())
        print(f"Initialized {project}; models={len(seeded.catalog.models)}; workflows=3.")
        engine.dispose()
    elif args.service == "api":
        import uvicorn

        uvicorn.run(
            "coastmas.app.production:create_production_app",
            factory=True,
            host=configuration_value("COASTMAS_HOST", "127.0.0.1"),
            port=int(configuration_value("COASTMAS_PORT", "58000")),
        )
    else:
        from coastmas.worker.runtime import WorkflowWorker, create_queue

        worker = WorkflowWorker(
            database_engine(),
            BuiltinRuntimeRegistry(sample_directory()),
            object_store(),
            work_root=Path(
                configuration_value("COASTMAS_WORK_ROOT", str(project_root() / "artifacts/runtime"))
            ),
        )
        queue = create_queue(
            worker,
            broker_url=configuration_value("REDIS_URL", "redis://127.0.0.1:56379/0"),
            queue_name=configuration_value("COASTMAS_QUEUE_NAME", "coastmas"),
        )
        if args.service == "worker":
            queue.worker_main(["worker", "--pool=solo", "--loglevel=INFO"])
        else:
            schedule = worker.work_root / "celerybeat"
            schedule.parent.mkdir(parents=True, exist_ok=True)
            queue.start(["beat", "--loglevel=INFO", "--schedule=" + str(schedule)])


if __name__ == "__main__":
    main()
