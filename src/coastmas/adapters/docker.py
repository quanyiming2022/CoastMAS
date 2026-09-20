"""Maintainer-registered containers run only by a trusted local worker.

No Docker socket is exposed to the API or model container. Images are pinned;
network, capabilities and writable root filesystem are disabled. Only the
worker-created request directory is mounted read-only. Creation and execution
are separate so an uncertain create never starts a scientific computation.
"""

import hashlib
import json
import math
import os
import re
import subprocess
import time
from dataclasses import dataclass, replace
from pathlib import Path
from uuid import uuid4

from coastmas.adapters.runtime import CLIAdapter, RunRequest
from coastmas.core.errors import CoastMASError


@dataclass(frozen=True)
class ContainerModel:
    image: str
    command: tuple[str, ...]
    cpus: float = 1.0
    memory_mb: int = 256
    pids: int = 64


class DockerAdapter(CLIAdapter):
    def __init__(
        self,
        models: dict[str, ContainerModel],
        *,
        docker: str,
        owner: str | None = None,
        max_output_bytes: int = 1048576,
    ):
        if not Path(docker).is_absolute():
            raise CoastMASError("MODEL_ERROR", "Docker executable must be an absolute path")
        for model in models.values():
            if re.fullmatch(r"(?:[A-Za-z0-9._:/-]+@)?sha256:[a-f0-9]{64}", model.image) is None:
                raise CoastMASError("MODEL_ERROR", "container image must use an immutable digest")
            if not model.command or not model.command[0].startswith("/"):
                raise CoastMASError(
                    "MODEL_ERROR", "registered container entrypoint must be absolute"
                )
            if (
                not math.isfinite(model.cpus)
                or not 0 < model.cpus <= 8
                or not 16 <= model.memory_mb <= 8192
                or not 8 <= model.pids <= 1024
            ):
                raise CoastMASError("MODEL_ERROR", "container resources exceed runner policy")
        self.models = dict(models)
        self.docker = docker
        self.owner = owner or uuid4().hex
        if re.fullmatch(r"[a-zA-Z0-9-]{1,64}", self.owner) is None:
            raise CoastMASError("MODEL_ERROR", "invalid container owner identifier")
        super().__init__({name: () for name in models}, max_output_bytes)

    def name(self, directory: Path) -> str:
        return (
            "coastmas-model-"
            + hashlib.sha256((self.owner + str(directory)).encode()).hexdigest()[:32]
        )

    def prepare(self, request: RunRequest) -> Path:
        directory = super().prepare(request)
        (directory / "parameters.json").write_text(json.dumps(request.parameters, allow_nan=False))
        return directory

    def arguments(self, request: RunRequest, directory: Path) -> list[str]:
        return [self.docker, "start", "--attach", self.name(directory)]

    def execute(self, request: RunRequest, directory: Path) -> tuple[bytes, int, float]:
        model = self.models[request.handler]
        name = self.name(directory)
        if "," in str(directory):
            raise CoastMASError("VALIDATION_ERROR", "container work directory cannot contain comma")
        arguments = [
            self.docker,
            "create",
            "--pull",
            "never",
            "--name",
            name,
            "--label",
            f"coastmas.adapter={self.owner}",
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--cpus",
            str(model.cpus),
            "--memory",
            f"{model.memory_mb}m",
            "--memory-swap",
            f"{model.memory_mb}m",
            "--pids-limit",
            str(model.pids),
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "--workdir",
            "/work",
            "--mount",
            f"type=bind,source={directory},target=/work,readonly",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=16m",
            "--entrypoint",
            model.command[0],
            model.image,
            *model.command[1:],
        ]
        environment = {"PATH": os.defpath, "LANG": "C.UTF-8"}
        started = time.monotonic()
        try:
            created = subprocess.run(
                arguments,
                capture_output=True,
                env=environment,
                timeout=min(15, request.timeout_seconds),
                check=False,
            )
            if created.returncode != 0:
                raise CoastMASError(
                    "CONTAINER_CREATE_ERROR", "registered container could not be created"
                )
            remaining = request.timeout_seconds - (time.monotonic() - started)
            if remaining <= 0:
                raise CoastMASError("TIMEOUT", "container deadline expired during preparation")
            result, code, _ = super().execute(
                replace(request, timeout_seconds=remaining), directory
            )
            return result, code, time.monotonic() - started
        except subprocess.TimeoutExpired as exc:
            raise CoastMASError(
                "TIMEOUT", "container preparation timeout; execution not started"
            ) from exc
        finally:
            try:
                removed = subprocess.run(
                    [self.docker, "rm", "--force", name],
                    capture_output=True,
                    timeout=10,
                    env=environment,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise CoastMASError(
                    "CONTAINER_CLEANUP_ERROR", "owned container cleanup timeout"
                ) from exc
            if removed.returncode != 0 and b"No such container" not in removed.stderr:
                raise CoastMASError("CONTAINER_CLEANUP_ERROR", "owned container cleanup failed")
