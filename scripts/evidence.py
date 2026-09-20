"""Execute an actual command and preserve its exit code and source identity."""

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from urllib.parse import quote, quote_plus

ROOT = Path(__file__).resolve().parents[1]


def configured_secrets() -> list[str]:
    configuration = dict(os.environ)
    environment = ROOT / ".env"
    if environment.exists():
        for line in environment.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                configuration.setdefault(key, value)
    return [
        value
        for key, value in configuration.items()
        if value
        and any(marker in key.upper() for marker in ("PASSWORD", "SECRET", "TOKEN", "API_KEY"))
    ]


def redact_secrets(content: str, secrets: list[str]) -> str:
    variants = {
        variant
        for secret in secrets
        if secret
        for variant in (
            secret,
            quote(secret, safe=""),
            quote_plus(secret),
            json.dumps(secret)[1:-1],
        )
    }
    for value in sorted(variants, key=len, reverse=True):
        content = content.replace(value, "[REDACTED]")
    return content


def source_digest() -> str:
    digest = hashlib.sha256()
    excluded = {"__pycache__", "node_modules", ".pytest_cache", "dist", ".next", ".venv"}
    paths: set[Path] = set()
    for folder in ("src", "tests", "scripts", "migrations", "deploy", "apps", "sample-data"):
        for path in (ROOT / folder).rglob("*"):
            relative = path.relative_to(ROOT)
            if (
                path.is_file()
                and not path.is_symlink()
                and not excluded.intersection(relative.parts)
            ):
                if not path.name.startswith(".env") and path.suffix != ".pyc":
                    paths.add(path)
    for pattern in (
        "pyproject.toml",
        "requirements*.txt",
        "alembic.ini",
        "docker-compose*.yml",
        "Makefile",
        "Dockerfile*",
    ):
        paths.update(path for path in ROOT.glob(pattern) if path.is_file())
    for path in sorted(paths):
        digest.update(str(path.relative_to(ROOT)).encode())
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("name")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    arguments = parser.parse_args()
    if not arguments.name.replace("-", "").replace("_", "").isalnum():
        parser.error("evidence name must be a simple identifier")
    command = arguments.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error("command is required")
    secrets = configured_secrets()
    if any(redact_secrets(argument, secrets) != argument for argument in command):
        parser.error("command contains a configured secret; pass it through the environment")
    directory = ROOT / "artifacts" / "evidence"
    directory.mkdir(parents=True, exist_ok=True)
    started = datetime.now(UTC)
    identifier = started.strftime("%Y%m%dT%H%M%S%fZ") + "-" + arguments.name
    log = directory / (identifier + ".log")
    before = source_digest()
    descriptor = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as output:
        result = subprocess.run(
            command, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT, check=False
        )
    raw_log = log.read_text(errors="replace")
    sanitized_log = redact_secrets(raw_log, secrets)
    log.write_text(sanitized_log)
    after = source_digest()
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=False
    )
    versions: dict[str, str | None] = {}
    for package in ("pydantic", "numpy", "scipy", "rasterio", "fastapi", "SQLAlchemy", "celery"):
        try:
            versions[package] = version(package)
        except PackageNotFoundError:
            versions[package] = None
    record = {
        "name": arguments.name,
        "log_redaction_applied": raw_log != sanitized_log,
        "log_redaction_policy": "configured secrets, literal/URL/JSON representations",
        "command": command,
        "started_at": started.isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
        "exit_code": result.returncode,
        "status": "PASS" if result.returncode == 0 and before == after else "FAIL",
        "source_sha256": before,
        "git_commit": revision.stdout.strip() if revision.returncode == 0 else None,
        "dependencies": versions,
        "source_changed_during_run": before != after,
        "python": sys.version,
        "platform": platform.platform(),
        "log": str(log.relative_to(ROOT)),
    }
    path = directory / (identifier + ".json")
    path.write_text(json.dumps(record, indent=2) + "\n")
    print(
        json.dumps(
            {
                "status": record["status"],
                "exit_code": result.returncode,
                "evidence": str(path.relative_to(ROOT)),
            }
        )
    )
    return result.returncode if result.returncode != 0 else (0 if before == after else 1)


if __name__ == "__main__":
    raise SystemExit(main())
