"""Shared request-scoped database sessions and authenticated identities."""

from collections.abc import Iterator
from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from coastmas.adapters.storage import S3ArtifactStore, local_storage_settings
from coastmas.configuration import configuration_value
from coastmas.persistence.auth import authenticate


def session_dependency(request: Request) -> Iterator[Session]:
    engine = cast(Engine, request.app.state.engine)
    with Session(engine) as session:
        yield session


DatabaseSession = Annotated[Session, Depends(session_dependency)]


def user_dependency(request: Request, session: DatabaseSession) -> str:
    return authenticate(
        session,
        request.cookies.get("coastmas_session"),
        csrf_token=request.headers.get("X-CSRF-Token"),
        require_csrf=request.method not in {"GET", "HEAD", "OPTIONS"},
    )


CurrentUser = Annotated[str, Depends(user_dependency)]


def artifact_store(request: Request) -> S3ArtifactStore:
    store = cast(S3ArtifactStore | None, request.app.state.artifact_store)
    if store is not None:
        return store
    return S3ArtifactStore(
        local_storage_settings(), bucket=configuration_value("S3_BUCKET", "coastmas")
    )
