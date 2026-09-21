"""Application factory for the independently runnable API and same-origin web UI."""

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from redis import Redis
from sqlalchemy import create_engine, text

from coastmas.adapters.source_registry import load_sources
from coastmas.app.api import create_app
from coastmas.app.readiness import register_readiness
from coastmas.configuration import configuration_value
from coastmas.persistence.database import local_database_url
from coastmas.runtime_bootstrap import (
    BuiltinRuntimeRegistry,
    configured_provider,
    database_engine,
    object_store,
    project_root,
    sample_directory,
)


def create_production_app() -> FastAPI:
    app = create_app(
        database_engine(),
        BuiltinRuntimeRegistry(sample_directory()),
        object_store(),
        configured_provider(),
    )
    sources = configuration_value("COASTMAS_DATA_SOURCES_CONFIG", "disabled")
    app.state.source_registry = load_sources(None if sources == "disabled" else Path(sources))
    # A separate small pool keeps readiness bounded even if the application pool is busy.
    probe_engine = create_engine(
        local_database_url(),
        pool_size=1,
        max_overflow=0,
        pool_timeout=3,
        connect_args={"connect_timeout": 3, "options": "-c statement_timeout=3000"},
    )
    probe_store = object_store()
    probe_queue = Redis.from_url(
        configuration_value("REDIS_URL", "redis://127.0.0.1:56379/0"),
        socket_connect_timeout=3,
        socket_timeout=3,
    )

    def database_ready() -> None:
        with probe_engine.connect() as connection:
            connection.execute(text("SELECT 1"))

    register_readiness(
        app,
        {
            "database": database_ready,
            "object_storage": lambda: probe_store.client.head_bucket(Bucket=probe_store.bucket),
            "queue": probe_queue.ping,
        },
    )
    distribution = Path(
        configuration_value("COASTMAS_WEB_DIRECTORY", str(project_root() / "apps/web/dist"))
    ).resolve()

    register_web(app, distribution)
    return app


def register_web(app: FastAPI, distribution: Path) -> None:
    """Serve frontend documents without confusing dotted resource IDs with assets."""

    @app.get("/{path:path}", include_in_schema=False)
    def web(path: str, request: Request) -> FileResponse:
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404, detail="API route not found")
        target = (distribution / path).resolve()
        if not target.is_relative_to(distribution):
            raise HTTPException(status_code=404, detail="Page not found")
        if not target.is_file():
            document_request = "text/html" in request.headers.get("accept", "")
            if Path(path).suffix and (not document_request or path.startswith("assets/")):
                raise HTTPException(status_code=404, detail="Asset not found")
            target = distribution / "index.html"
        if not target.is_file():
            raise HTTPException(status_code=503, detail="Web application build is unavailable")
        return FileResponse(
            target, headers={"Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff"}
        )
