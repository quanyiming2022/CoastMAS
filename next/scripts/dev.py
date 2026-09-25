"""Initialize or serve the isolated next runtime; never select the legacy database."""

import argparse
import json
import os
import secrets
import signal
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "vendor")]


def load(path):
    from coastmas_next.config import Settings

    data = json.loads(path.read_text())
    web_root = Path(data.get("web_root", ROOT / "web/dist")).resolve()
    if data.get("web_root") and not (web_root / "index.html").is_file():
        raise ValueError("Configured frontend build is missing; refusing a mixed release")
    return Settings(
        runtime_catalog=Path(data["runtime_catalog"]) if data.get("runtime_catalog") else None,
        web_root=web_root if (web_root / "index.html").is_file() else None,
        database_url=data["database_url"],
        storage_root=Path(data["storage_root"]),
        local_sources=tuple(Path(p) for p in data.get("local_sources", [])),
    )


def initialize(config_path, database, storage_root):
    from coastmas_next.app import create_app
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import URL

    if not database.startswith("coastmas_next_") or not database.replace("_", "").isalnum():
        raise ValueError("Explicit isolated coastmas_next_ database required")
    if config_path.exists():
        raise ValueError("Configuration already exists; not replacing an existing namespace")
    env = {}
    for line in (ROOT.parent / ".env").read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            env[key] = value
    url = URL.create(
        "postgresql+psycopg",
        username=env.get("POSTGRES_USER", "coastmas"),
        password=env["POSTGRES_PASSWORD"],
        host="127.0.0.1",
        port=int(env.get("POSTGRES_PORT", 55432)),
        database="postgres",
    )
    engine = create_engine(url, isolation_level="AUTOCOMMIT")
    with engine.connect() as connection:
        if connection.scalar(
            text("SELECT 1 FROM pg_database WHERE datname=:database"), {"database": database}
        ):
            raise ValueError("Database already exists; refusing to initialize over existing data")
        connection.execute(text('CREATE DATABASE "' + database + '"'))
    engine.dispose()
    data = {
        "database_url": url.set(database=database).render_as_string(hide_password=False),
        "storage_root": str(storage_root.resolve()),
        "local_sources": [str(ROOT.parent.parent / "data_quan")],
    }
    config_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(config_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as output:
        json.dump(data, output)
    settings = load(config_path)
    store = create_app(settings).state.store
    store.initialize()
    password = secrets.token_urlsafe(24)
    actor = store.create_account("admin@coastmas.local", password, system_admin=True)
    project = store.create_project(actor, "CoastMAS 新版研究项目")
    access = config_path.with_name(config_path.stem + "-access.json")
    fd = os.open(access, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as output:
        json.dump(
            {"email": "admin@coastmas.local", "password": password, "project_id": project}, output
        )
    print(json.dumps({"database": database, "access_file": str(access), "project_id": project}))


def run_worker(worker, stop):
    while not stop.is_set():
        if not worker.run_once():
            stop.wait(0.5)


def main():
    from coastmas_next.app import create_app
    from coastmas_next.store import Store
    from coastmas_next.worker import Worker

    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["init", "api", "worker"])
    parser.add_argument("--config", type=Path, default=ROOT / ".state/settings.json")
    parser.add_argument("--database", default="coastmas_next_dev_20260924")
    parser.add_argument("--storage", type=Path, default=ROOT / ".state/objects")
    parser.add_argument("--port", type=int, default=58010)
    args = parser.parse_args()
    if args.action == "init":
        initialize(args.config, args.database, args.storage)
        return
    settings = load(args.config)
    store = Store(settings)
    store.initialize()
    if args.action == "api":
        import uvicorn

        uvicorn.run(create_app(settings), host="127.0.0.1", port=args.port)
    else:
        stop = threading.Event()
        signal.signal(signal.SIGTERM, lambda *_: stop.set())
        signal.signal(signal.SIGINT, lambda *_: stop.set())
        run_worker(Worker(store), stop)


if __name__ == "__main__":
    main()
