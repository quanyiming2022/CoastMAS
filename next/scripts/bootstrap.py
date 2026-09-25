"""Create one new local namespace. Never reads or resets the legacy environment."""

import argparse
import json
import os
import re
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "vendor")]


def initialize(name, email, sources):
    from coastmas_next.app import create_app
    from coastmas_next.config import Settings

    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}", name):
        raise ValueError("Namespace must be 1–64 letters, digits, hyphens or underscores")
    approved = []
    for raw in sources:
        path = Path(raw).resolve(strict=True)
        if not path.is_dir():
            raise ValueError("Local source must be an existing directory")
        approved.append(str(path))
    root = ROOT / ".state" / name
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    settings = Settings(
        database_url="sqlite:///" + str(root / "coastmas_next.db"),
        storage_root=root / "objects",
        local_sources=tuple(Path(p) for p in approved),
    )
    store = create_app(settings).state.store
    store.initialize()
    password = secrets.token_urlsafe(24)
    actor = store.create_account(email, password, system_admin=True)
    project = store.create_project(actor, "CoastMAS 新研究项目")
    config = root / "settings.json"
    access = root / "settings-access.json"
    for path, value in [
        (
            config,
            {
                "database_url": settings.database_url,
                "storage_root": str(settings.storage_root),
                "local_sources": approved,
            },
        ),
        (access, {"email": email, "password": password, "project_id": project}),
    ]:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
    store.engine.dispose()
    return {"config": str(config), "access_file": str(access), "project_id": project}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True)
    parser.add_argument("--email", default="admin@coastmas.local")
    parser.add_argument("--local-source", action="append", default=[])
    args = parser.parse_args()
    print(json.dumps(initialize(args.name, args.email, args.local_source), ensure_ascii=False))


if __name__ == "__main__":
    main()
