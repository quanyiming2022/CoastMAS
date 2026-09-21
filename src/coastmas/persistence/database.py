"""Connection construction avoids logging connection-string secrets."""

import os
from pathlib import Path

from sqlalchemy.engine import URL


def local_database_url(database: str | None = None) -> URL:
    root = Path(__file__).resolve().parents[3]
    environment = root / ".env"
    local: dict[str, str] = {}
    if environment.exists():
        for line in environment.read_text().splitlines():
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                local[key] = value
    password = os.environ.get("POSTGRES_PASSWORD", local.get("POSTGRES_PASSWORD"))
    if not password:
        raise RuntimeError("POSTGRES_PASSWORD is required")
    return URL.create(
        "postgresql+psycopg",
        username=os.environ.get("POSTGRES_USER", "coastmas"),
        password=password,
        host=os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        port=int(os.environ.get("POSTGRES_PORT", "55432")),
        database=database
        if database is not None
        else os.environ.get("POSTGRES_DB", local.get("POSTGRES_DB", "coastmas")),
    )
