"""Shared request-scoped database sessions and authenticated identities."""

from collections.abc import Iterator
from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy import Engine
from sqlalchemy.orm import Session

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
