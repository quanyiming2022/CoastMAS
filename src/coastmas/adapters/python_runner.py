"""Private entry point for trusted callbacks with structured failure diagnostics."""

import json
import sys
import traceback
from pathlib import Path
from typing import cast

# Exact untyped boundary: only private maintainer-generated callback serialization.
import cloudpickle  # type: ignore[import-untyped]
from pydantic import JsonValue, TypeAdapter

from coastmas.adapters.runtime import Handler
from coastmas.core.errors import CoastMASError


def main() -> int:
    if len(sys.argv) != 4:
        raise SystemExit("private runner expects three file arguments")
    schema = TypeAdapter(dict[str, JsonValue])
    try:
        with Path(sys.argv[1]).open("rb") as source:
            handler = cast(Handler, cloudpickle.load(source))
        inputs = schema.validate_json(Path(sys.argv[2]).read_text())
        parameters = schema.validate_json(Path(sys.argv[3]).read_text())
        result = schema.validate_python(handler(inputs, parameters))
        print(json.dumps(result, allow_nan=False))
        return 0
    except Exception as exc:
        frames = [
            f"{Path(frame.filename).name}:{frame.name}:{frame.lineno}"
            for frame in traceback.extract_tb(exc.__traceback__)
        ]
        error = {
            "code": exc.code if isinstance(exc, CoastMASError) else "MODEL_ERROR",
            "message": exc.message
            if isinstance(exc, CoastMASError)
            else "trusted model failed; inspect diagnostic frames",
            "details": {"exception_type": type(exc).__name__, "frames": frames},
        }
        # No raw exception arguments, local variables, source lines or input values.
        with Path("failure.json").open("x") as output:
            output.write(json.dumps(error, allow_nan=False))
        return 70


if __name__ == "__main__":
    raise SystemExit(main())
