"""Execute an actual command and preserve its exit code and source identity."""

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def source_digest() -> str:
    digest = hashlib.sha256()
    for folder in ("src", "tests", "scripts"):
        for path in sorted((ROOT / folder).rglob("*.py")):
            digest.update(str(path.relative_to(ROOT)).encode())
            digest.update(path.read_bytes())
    for name in ("pyproject.toml", "requirements-lock.txt"):
        digest.update((ROOT / name).read_bytes())
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
    directory = ROOT / "artifacts" / "evidence"
    directory.mkdir(parents=True, exist_ok=True)
    started = datetime.now(UTC)
    identifier = started.strftime("%Y%m%dT%H%M%S%fZ") + "-" + arguments.name
    log = directory / (identifier + ".log")
    before = source_digest()
    with log.open("w") as output:
        result = subprocess.run(
            command, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT, check=False
        )
    after = source_digest()
    record = {
        "name": arguments.name,
        "command": command,
        "started_at": started.isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
        "exit_code": result.returncode,
        "status": "PASS" if result.returncode == 0 and before == after else "FAIL",
        "source_sha256": before,
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
