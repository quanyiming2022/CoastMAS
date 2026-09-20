"""Local configuration lookup; callers never print returned secret values."""

import os
from pathlib import Path


def configuration_value(name: str, default: str | None = None) -> str:
    value = os.environ.get(name)
    if value is None:
        local = Path(__file__).resolve().parents[2] / ".env"
        if local.exists():
            for line in local.read_text().splitlines():
                if line.startswith(name + "="):
                    value = line.split("=", 1)[1]
                    break
    if value is None:
        value = default
    if value is None or value == "":
        raise RuntimeError(f"required configuration {name} is unavailable")
    return value
