"""Argon2 passwords and hashed, revocable opaque sessions."""

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from coastmas.core.errors import CoastMASError
from coastmas.persistence.schema import AuthSession, User

HASHER = PasswordHasher()
DUMMY_HASH = HASHER.hash(secrets.token_urlsafe(32))


def hash_password(password: str) -> str:
    if len(password) < 12 or len(password) > 256:
        raise CoastMASError("VALIDATION_ERROR", "password length must be between 12 and 256")
    return HASHER.hash(password)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True)
class LoginTokens:
    user_id: str
    session_token: str
    csrf_token: str


def login(session: Session, email: str, password: str) -> LoginTokens:
    user = session.scalar(select(User).where(User.email == email.strip().lower()))
    password_hash = user.password_hash if user is not None else DUMMY_HASH
    verified: bool
    try:
        verified = HASHER.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        verified = False
    if not verified or user is None or not user.active:
        raise CoastMASError("AUTHENTICATION_ERROR", "invalid login credentials")
    if HASHER.check_needs_rehash(user.password_hash):
        user.password_hash = HASHER.hash(password)
    token, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
    session.add(
        AuthSession(
            token_hash=token_digest(token),
            user_id=user.id,
            csrf_hash=token_digest(csrf),
            expires_at=datetime.now(UTC) + timedelta(hours=8),
        )
    )
    session.flush()
    return LoginTokens(user.id, token, csrf)


def authenticate(
    session: Session,
    token: str | None,
    *,
    csrf_token: str | None = None,
    require_csrf: bool = False,
) -> str:
    if token is None or len(token) > 256:
        raise CoastMASError("AUTHENTICATION_ERROR", "login required")
    record = session.get(AuthSession, token_digest(token))
    user = session.get(User, record.user_id) if record is not None else None
    if record is None or record.expires_at <= datetime.now(UTC) or user is None or not user.active:
        raise CoastMASError("AUTHENTICATION_ERROR", "session expired or unavailable")
    if require_csrf:
        if csrf_token is None or not hmac.compare_digest(
            token_digest(csrf_token), record.csrf_hash
        ):
            raise CoastMASError("CSRF_ERROR", "request verification failed")
    return user.id


def logout(session: Session, token: str) -> None:
    record = session.get(AuthSession, token_digest(token))
    if record is not None:
        session.delete(record)
        session.flush()
