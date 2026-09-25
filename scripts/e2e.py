"""Run real browser tests in disposable project-owned infrastructure namespaces.

Only this invocation's random database, bucket, queue keys and child processes are
removed. Credentials and logs stay private under the ignored runtime directory.
The user's demo workspace and evidence are never reused as test fixtures.
"""

import json
import os
import secrets
import socket
import subprocess
import sys
import time
from contextlib import ExitStack
from pathlib import Path
from uuid import uuid4

import httpx
from redis import Redis
from sqlalchemy import create_engine, text

from coastmas.adapters.storage import S3ArtifactStore, local_storage_settings
from coastmas.configuration import configuration_value
from coastmas.persistence.database import local_database_url

ROOT = Path(__file__).resolve().parents[1]


def available_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def private_json(path: Path, value: object) -> None:
    with open(path, "x", opener=lambda name, flags: os.open(name, flags, 0o600)) as stream:
        json.dump(value, stream)


def stop(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def wait_ready(url: str, processes: list[subprocess.Popen[bytes]]) -> None:
    deadline = time.monotonic() + 60
    last_status = "not reached"
    with httpx.Client(timeout=3) as client:
        while time.monotonic() < deadline:
            if any(process.poll() is not None for process in processes):
                raise RuntimeError("isolated service exited; inspect private runtime logs")
            try:
                response = client.get(url)
                last_status = str(response.status_code)
                if response.status_code == 200:
                    return
            except httpx.TransportError:
                last_status = "connection unavailable"
            time.sleep(0.25)
    raise RuntimeError("isolated readiness timed out: " + last_status)


def main() -> int:
    identifier = uuid4().hex
    database = "coastmas_e2e_" + identifier
    bucket = "coastmas-e2e-" + identifier
    queue = "coastmas-e2e-" + identifier
    project = str(uuid4())
    runtime = ROOT / "artifacts/runtime" / database
    runtime.mkdir(mode=0o700, parents=True)
    api_port, source_port = available_port(), available_port()
    while source_port == api_port:
        source_port = available_port()
    access = {"email": f"{identifier}@e2e.invalid", "password": secrets.token_urlsafe(32)}
    private_json(runtime / "access.json", access)
    private_json(
        runtime / "sources.json",
        {
            "demo-csv": {
                "kind": "http",
                "name": "SYNTHETIC isolated acceptance source",
                "revision": 1,
                "projects": [project],
                "url": f"http://127.0.0.1:{source_port}/observations.csv",
                "allow_private": True,
            }
        },
    )
    base_url = f"http://127.0.0.1:{api_port}"
    broker_url = configuration_value("REDIS_URL", "redis://127.0.0.1:56379/0")
    environment = os.environ | {
        "POSTGRES_DB": database,
        "S3_BUCKET": bucket,
        "COASTMAS_QUEUE_NAME": queue,
        "COASTMAS_PROJECT_ID": project,
        "COASTMAS_ADMIN_EMAIL": access["email"],
        "COASTMAS_ADMIN_PASSWORD": access["password"],
        "COASTMAS_LLM_ENABLED": "false",
        "COASTMAS_HOST": "127.0.0.1",
        "COASTMAS_PORT": str(api_port),
        "COASTMAS_WORK_ROOT": str(runtime / "worker"),
        "REDIS_URL": broker_url,
        "COASTMAS_DATA_SOURCES_CONFIG": str(runtime / "sources.json"),
        "COASTMAS_E2E_ACCESS_FILE": str(runtime / "access.json"),
        "COASTMAS_E2E_URL": base_url,
    }
    business_root = os.environ.get("COASTMAS_E2E_BUSINESS_ROOT")
    if business_root:
        environment["COASTMAS_LOCAL_IMPORT_ROOTS"] = json.dumps(
            {
                "business-acceptance": {
                    "path": str(Path(business_root).resolve(strict=True)),
                    "project_ids": [project],
                }
            }
        )
    administrative = create_engine(local_database_url(), isolation_level="AUTOCOMMIT")
    store = S3ArtifactStore(local_storage_settings(), bucket=bucket)
    broker = Redis.from_url(broker_url)
    processes: list[subprocess.Popen[bytes]] = []

    def cleanup_database() -> None:
        with administrative.connect() as connection:
            connection.execute(text(f'DROP DATABASE "{database}" WITH (FORCE)'))

    def cleanup_objects() -> None:
        pages = store.client.get_paginator("list_objects_v2")
        for page in pages.paginate(Bucket=bucket):
            for item in page.get("Contents", []):
                store.client.delete_object(Bucket=bucket, Key=item["Key"])
        store.client.delete_bucket(Bucket=bucket)

    def cleanup_queue() -> None:
        for key in broker.scan_iter(match=queue + ":*"):
            broker.delete(key)

    with ExitStack() as resources:
        resources.callback(administrative.dispose)
        resources.callback(broker.close)
        with administrative.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{database}"'))
        resources.callback(cleanup_database)
        store.ensure_bucket()
        resources.callback(cleanup_objects)
        resources.callback(cleanup_queue)
        init_log = resources.enter_context((runtime / "init.log").open("wb"))
        subprocess.run(
            [sys.executable, "-m", "coastmas", "init"],
            cwd=ROOT,
            env=environment,
            stdout=init_log,
            stderr=subprocess.STDOUT,
            check=True,
        )
        commands = {
            "source": [
                sys.executable,
                "scripts/serve_acceptance_source.py",
                "--port",
                str(source_port),
            ],
            **{
                name: [sys.executable, "-m", "coastmas", name] for name in ("api", "worker", "beat")
            },
        }
        for name, command in commands.items():
            log = resources.enter_context((runtime / (name + ".log")).open("wb"))
            process = subprocess.Popen(
                command, cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT
            )
            processes.append(process)
            resources.callback(stop, process)
        wait_ready(base_url + "/health/ready", processes)
        wait_ready(f"http://127.0.0.1:{source_port}/observations.csv", processes)
        print("Isolated browser environment ready:", database, flush=True)
        completed = subprocess.run(
            [
                "npm",
                "--prefix",
                "apps/web",
                "run",
                "e2e",
                "--",
                "--output",
                str(runtime / "playwright"),
                *sys.argv[1:],
            ],
            cwd=ROOT,
            env=environment,
            check=False,
        )
        result = completed.returncode
    print(
        "Isolated resources removed; private logs retained:", runtime.relative_to(ROOT), flush=True
    )
    return result


if __name__ == "__main__":
    raise SystemExit(main())
