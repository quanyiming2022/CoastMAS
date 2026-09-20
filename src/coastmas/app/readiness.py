"""Dependency readiness is distinct from process liveness and never exposes secrets."""

import logging
from collections.abc import Callable

from fastapi import FastAPI
from fastapi.responses import JSONResponse

LOG = logging.getLogger("coastmas.readiness")


def register_readiness(app: FastAPI, checks: dict[str, Callable[[], object]]) -> None:
    # Checks must configure bounded connection/read timeouts at their client boundary.
    @app.get("/health/live")
    def live() -> dict[str, str]:
        return {"status": "alive"}

    @app.get("/health/ready")
    def ready() -> JSONResponse:
        dependencies: dict[str, str] = {}
        for name, check in checks.items():
            try:
                check()
                dependencies[name] = "ready"
            except Exception as exc:
                LOG.warning("Dependency %s failed: %s", name, type(exc).__name__)
                dependencies[name] = "unavailable"
        available = all(value == "ready" for value in dependencies.values())
        return JSONResponse(
            status_code=200 if available else 503,
            content={
                "status": "ready" if available else "unavailable",
                "dependencies": dependencies,
            },
        )
