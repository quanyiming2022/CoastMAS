"""Trusted Python/CLI execution in isolated temporary working directories.

Only application-maintainer supplied handlers and argument templates can be
registered. User uploads are never deserialized. Both adapters run child
processes and propagate timeout/cancellation to the entire child process group.
"""

import json
import math
import os
import re
import selectors
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

# cloudpickle lacks inline typing; only dump of trusted in-process callbacks is used.
import cloudpickle  # type: ignore[import-untyped]
from pydantic import JsonValue, TypeAdapter, ValidationError

from coastmas.core.errors import CoastMASError

OUTPUT_SCHEMA = TypeAdapter(dict[str, JsonValue])
Handler = Callable[[dict[str, JsonValue], dict[str, JsonValue]], dict[str, JsonValue]]


@dataclass(frozen=True)
class RunRequest:
    handler: str
    inputs: dict[str, JsonValue]
    parameters: dict[str, JsonValue]
    work_root: Path
    timeout_seconds: float
    cancel: threading.Event = field(default_factory=threading.Event)


@dataclass(frozen=True)
class AdapterResult:
    outputs: dict[str, JsonValue]
    exit_code: int
    elapsed_seconds: float


class ModelAdapter(Protocol):
    def prepare(self, request: RunRequest) -> Path: ...
    def validate(self, request: RunRequest) -> None: ...
    def execute(self, request: RunRequest, directory: Path) -> tuple[bytes, int, float]: ...
    def collect(self, output: bytes, exit_code: int, elapsed: float) -> AdapterResult: ...
    def cleanup(self, directory: Path) -> None: ...


class CLIAdapter:
    def __init__(self, templates: dict[str, tuple[str, ...]], max_output_bytes: int = 1048576):
        if max_output_bytes <= 0:
            raise ValueError("positive output budget required")
        self.templates = dict(templates)
        self.max_output_bytes = max_output_bytes

    def validate(self, request: RunRequest) -> None:
        if request.handler not in self.templates:
            raise CoastMASError("MODEL_ERROR", "handler must be explicitly registered")
        if not math.isfinite(request.timeout_seconds) or not 0 < request.timeout_seconds <= 86400:
            raise CoastMASError("VALIDATION_ERROR", "invalid execution timeout")
        if request.cancel.is_set():
            raise CoastMASError("CANCELLED", "execution cancelled before start")
        json.dumps({"inputs": request.inputs, "parameters": request.parameters}, allow_nan=False)

    def prepare(self, request: RunRequest) -> Path:
        request.work_root.mkdir(parents=True, exist_ok=True)
        directory = Path(tempfile.mkdtemp(prefix="coastmas-job-", dir=request.work_root))
        (directory / "input.json").write_text(json.dumps(request.inputs, allow_nan=False))
        return directory

    def arguments(self, request: RunRequest, directory: Path) -> list[str]:
        arguments = []
        for argument in self.templates[request.handler]:
            match = re.fullmatch(r"\{([a-zA-Z][a-zA-Z0-9_]*)\}", argument)
            if match:
                name = match.group(1)
                if name not in request.parameters:
                    raise CoastMASError("VALIDATION_ERROR", "registered command parameter missing")
                value = request.parameters[name]
                if not isinstance(value, (str, int, float, bool)):
                    raise CoastMASError("VALIDATION_ERROR", "command parameters must be scalar")
                argument = str(value)
                if len(argument) > 4096:
                    raise CoastMASError("VALIDATION_ERROR", "command parameter too long")
            arguments.append(argument)
        if not arguments or not Path(arguments[0]).is_absolute():
            raise CoastMASError("MODEL_ERROR", "registered executable must use an absolute path")
        return arguments

    @staticmethod
    def signal_group(identifier: int, signal_number: int) -> bool:
        # Darwin can briefly return EPERM while an empty group is being reaped.
        # Confirm disappearance via ESRCH; a persistent permission failure is never hidden.
        for attempt in range(3):
            try:
                os.killpg(identifier, signal_number)
                return True
            except ProcessLookupError:
                return False
            except PermissionError:
                if attempt == 2:
                    raise
                time.sleep(0.01)
        raise RuntimeError("unreachable signal retry state")

    @classmethod
    def terminate(cls, process: subprocess.Popen[bytes]) -> None:
        # The leader may already have exited while descendants retain its process group.
        if not cls.signal_group(process.pid, signal.SIGTERM):
            process.wait(timeout=2)
            return
        try:
            process.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            process.poll()
        cls.signal_group(process.pid, signal.SIGKILL)
        process.wait(timeout=2)

    def execution_environment(self) -> dict[str, str]:
        return {
            "PATH": os.defpath,
            "LANG": "C.UTF-8",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": str(Path(__file__).resolve().parents[2]),
        }

    def execute(self, request: RunRequest, directory: Path) -> tuple[bytes, int, float]:
        arguments = self.arguments(request, directory)
        environment = self.execution_environment()
        started = time.monotonic()
        process = subprocess.Popen(
            arguments,
            cwd=directory,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            shell=False,
        )
        output = bytearray()
        total = 0
        try:
            with selectors.DefaultSelector() as selector:
                if process.stdout is None or process.stderr is None:
                    raise CoastMASError("EXECUTION_ERROR", "process output channels unavailable")
                selector.register(process.stdout, selectors.EVENT_READ, "stdout")
                selector.register(process.stderr, selectors.EVENT_READ, "stderr")
                while selector.get_map():
                    if request.cancel.is_set():
                        raise CoastMASError("CANCELLED", "execution cancelled")
                    if time.monotonic() - started > request.timeout_seconds:
                        raise CoastMASError("TIMEOUT", "execution timeout")
                    for key, _ in selector.select(timeout=0.02):
                        chunk = os.read(key.fd, 8192)
                        if not chunk:
                            selector.unregister(key.fileobj)
                            continue
                        total += len(chunk)
                        if total > self.max_output_bytes:
                            raise CoastMASError(
                                "OUTPUT_LIMIT", "model output exceeds configured budget"
                            )
                        if key.data == "stdout":
                            output.extend(chunk)
                remaining = max(0.001, request.timeout_seconds - (time.monotonic() - started))
                try:
                    code = process.wait(timeout=remaining)
                except subprocess.TimeoutExpired as exc:
                    raise CoastMASError("TIMEOUT", "execution timeout") from exc
                if code != 0:
                    raise CoastMASError("EXECUTION_ERROR", f"model exited with code {code}")
                return bytes(output), code, time.monotonic() - started
        finally:
            self.terminate(process)
            if process.stdout is not None:
                process.stdout.close()
            if process.stderr is not None:
                process.stderr.close()

    def collect(self, output: bytes, exit_code: int, elapsed: float) -> AdapterResult:
        try:
            parsed = OUTPUT_SCHEMA.validate_json(output)
            json.dumps(parsed, allow_nan=False)
        except (ValidationError, ValueError) as exc:
            raise CoastMASError(
                "MODEL_OUTPUT_ERROR", "model output is not finite JSON object"
            ) from exc
        return AdapterResult(parsed, exit_code, elapsed)

    def cleanup(self, directory: Path) -> None:
        shutil.rmtree(directory)

    def run(self, request: RunRequest) -> AdapterResult:
        self.validate(request)
        directory = self.prepare(request)
        try:
            output, exit_code, elapsed = self.execute(request, directory)
            return self.collect(output, exit_code, elapsed)
        finally:
            self.cleanup(directory)


class PythonFunctionAdapter(CLIAdapter):
    def __init__(self, handlers: dict[str, Handler], max_output_bytes: int = 1048576):
        super().__init__({name: () for name in handlers}, max_output_bytes)
        self.handlers = dict(handlers)

    def execution_environment(self) -> dict[str, str]:
        environment = super().execution_environment()
        # Explicit instrumentation allowlist; no provider credentials or general env forwarding.
        # Coverage serializes absolute output paths, so temporary job cleanup loses no measurements.
        if "COVERAGE_PROCESS_CONFIG" in os.environ:
            environment["COVERAGE_PROCESS_CONFIG"] = os.environ["COVERAGE_PROCESS_CONFIG"]
        return environment

    def execute(self, request: RunRequest, directory: Path) -> tuple[bytes, int, float]:
        try:
            return super().execute(request, directory)
        except CoastMASError as exc:
            diagnostic = directory / "failure.json"
            if (
                exc.code == "EXECUTION_ERROR"
                and diagnostic.is_file()
                and diagnostic.stat().st_size <= 32768
            ):
                failure = OUTPUT_SCHEMA.validate_json(diagnostic.read_bytes())
                code, message, details = (
                    failure.get("code"),
                    failure.get("message"),
                    failure.get("details"),
                )
                if isinstance(code, str) and isinstance(message, str) and isinstance(details, dict):
                    raise CoastMASError(code, message, details) from exc
            raise

    def arguments(self, request: RunRequest, directory: Path) -> list[str]:
        # This pickle is generated from a maintainer's callback, never accepted from an upload.
        handler = directory / "trusted-handler.pkl"
        with handler.open("wb") as output:
            cloudpickle.dump(self.handlers[request.handler], output)
        (directory / "parameters.json").write_text(json.dumps(request.parameters, allow_nan=False))
        return [
            sys.executable,
            "-m",
            "coastmas.adapters.python_runner",
            str(handler),
            str(directory / "input.json"),
            str(directory / "parameters.json"),
        ]
