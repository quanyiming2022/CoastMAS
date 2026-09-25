"""Create a private intake report outside the original data directory."""

import argparse
import json
import os
from pathlib import Path
from typing import cast

from pydantic import JsonValue

from coastmas.core.business_intake import apply_declarations, inspect_directory


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--declarations", type=Path)
    args = parser.parse_args()
    root = args.source.resolve()
    output = args.output.resolve()
    if output.is_relative_to(root):
        parser.error("report must be outside the original source directory")
    if output.exists():
        parser.error("report already exists; use a new output name to preserve evidence")
    report = inspect_directory(root)
    if args.declarations:
        report = apply_declarations(report, json.loads(args.declarations.read_text()))
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(
        output, "x", encoding="utf-8", opener=lambda name, flags: os.open(name, flags, 0o600)
    ) as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
    print(
        json.dumps(
            {
                "report": str(output),
                "rasters": len(cast(list[JsonValue], report["rasters"])),
                "models": len(cast(list[JsonValue], report["models"])),
                "read_errors": len(cast(list[JsonValue], report["errors"])),
                "scientific_execution_ready": False,
            },
            ensure_ascii=False,
        )
    )
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
