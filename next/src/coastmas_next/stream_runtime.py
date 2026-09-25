"""One isolated original R fit, streamed bounded prediction batches, no uploaded code."""

import hashlib
import json
import os
import re
import selectors
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from uuid import uuid4

import numpy as np

from .store import Problem

RUNNER = Path(__file__).resolve().parents[2] / "runtime/stream.R"


class StreamModel:
    def __init__(
        self,
        *,
        image,
        handler,
        frame,
        parameters,
        work_root,
        cancelled,
        runner_sha256=None,
        timeout=3600,
    ):
        if not re.fullmatch(r"sha256:[a-f0-9]{64}", image) or handler not in {
            "ppci_mcdc",
            "ppr_ols",
        }:
            raise Problem(422, "RUNTIME_IDENTITY", "运行包必须固定到核验版本")
        self.docker = shutil.which("docker")
        if self.docker is None:
            raise Problem(503, "RUNTIME_UNAVAILABLE", "本机容器环境不可用")
        self.image, self.handler, self.frame, self.parameters = image, handler, frame, parameters
        self.root = Path(work_root)
        self.cancelled = cancelled
        self.expected_runner = runner_sha256
        self.deadline = time.monotonic() + timeout
        self.name = "coastmas-next-" + uuid4().hex
        self.directory = None
        self.process = None
        self.created = False
        self.buffer = bytearray()
        self.diagnostics = bytearray()
        self.result = None

    def check(self):
        if self.cancelled.is_set():
            raise Problem(409, "CANCELLED", "模型运行已取消")
        if time.monotonic() > self.deadline:
            raise Problem(504, "MODEL_TIMEOUT", "固定模型运行超过时间预算")

    def __enter__(self):
        try:
            content = RUNNER.read_bytes()
            if self.expected_runner and hashlib.sha256(content).hexdigest() != self.expected_runner:
                raise Problem(409, "RUNNER_CHANGED", "应用适配器与批准版本不一致")
            self.root.mkdir(parents=True, exist_ok=True)
            self.directory = Path(tempfile.mkdtemp(prefix="stream-", dir=self.root))
            (self.directory / "stream.R").write_bytes(content)
            (self.directory / "input.json").write_text(
                json.dumps(
                    {"frame": self.frame, "parameters": self.parameters, "handler": self.handler},
                    allow_nan=False,
                )
            )
            if "," in str(self.directory):
                raise Problem(422, "WORK_PATH", "运行目录不能包含逗号")
            args = [
                self.docker,
                "create",
                "--pull",
                "never",
                "-i",
                "--name",
                self.name,
                "--label",
                "coastmas.next.owner=" + self.name,
                "--network",
                "none",
                "--read-only",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--cpus",
                "2",
                "--memory",
                "1024m",
                "--memory-swap",
                "1024m",
                "--pids-limit",
                "128",
                "--user",
                f"{os.getuid()}:{os.getgid()}",
                "--mount",
                f"type=bind,source={self.directory},target=/work,readonly",
                "--tmpfs",
                "/tmp:rw,noexec,nosuid,size=64m",
                "--entrypoint",
                "/usr/bin/Rscript",
                self.image,
                "--vanilla",
                "/work/stream.R",
            ]
            creation = subprocess.run(args, capture_output=True, timeout=20, check=False)
            if creation.returncode:
                raise Problem(
                    503,
                    "CONTAINER_CREATE",
                    "无法创建已核验模型容器",
                    {"diagnostic": creation.stderr.decode(errors="replace")[-2000:]},
                )
            self.created = True
            self.process = subprocess.Popen(
                [self.docker, "start", "--attach", "--interactive", self.name],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
            )
            for pipe in (self.process.stdin, self.process.stdout, self.process.stderr):
                os.set_blocking(pipe.fileno(), False)
            ready = self.receive()
            if ready.get("ready") is not True:
                raise Problem(422, "MODEL_PROTOCOL", "原模型未完成一次训练")
            self.result = ready["result"]
            return self
        except BaseException:
            self.close()
            raise

    def receive(self):
        with selectors.DefaultSelector() as selector:
            selector.register(self.process.stdout, selectors.EVENT_READ, "stdout")
            selector.register(self.process.stderr, selectors.EVENT_READ, "stderr")
            while True:
                self.check()
                if b"\n" in self.buffer:
                    line, _, rest = self.buffer.partition(b"\n")
                    self.buffer = bytearray(rest)
                    try:
                        return json.loads(line)
                    except (ValueError, UnicodeError) as exc:
                        raise Problem(422, "MODEL_PROTOCOL", "模型输出不符合固定协议") from exc
                for event, _ in selector.select(0.1):
                    chunk = os.read(event.fd, 65536)
                    if not chunk:
                        selector.unregister(event.fileobj)
                        if event.data == "stdout":
                            raise Problem(
                                422,
                                "MODEL_FAILED",
                                "原模型进程结束，未提供完整结果",
                                {"diagnostic": self.diagnostics.decode(errors="replace")[-2000:]},
                            )
                    elif event.data == "stderr":
                        self.diagnostics.extend(chunk)
                        if len(self.diagnostics) > 65536:
                            raise Problem(422, "MODEL_DIAGNOSTICS_LIMIT", "模型诊断超出限制")
                    else:
                        self.buffer.extend(chunk)
                        if len(self.buffer) > 32 * 1024**2:
                            raise Problem(422, "MODEL_OUTPUT_LIMIT", "单批模型输出超过预算")

    def predict(self, values):
        array = np.asarray(values, dtype=float)
        if array.ndim != 2 or len(array) > 65536 or not np.isfinite(array).all():
            raise Problem(422, "PREDICT_BATCH", "预测批次必须有界且为有限二维数值")
        data = memoryview(
            (
                json.dumps({"values": array.tolist()}, allow_nan=False, separators=(",", ":"))
                + "\n"
            ).encode()
        )
        if len(data) > 32 * 1024**2:
            raise Problem(422, "MODEL_INPUT_LIMIT", "单批输入超出预算")
        with selectors.DefaultSelector() as selector:
            selector.register(self.process.stdin, selectors.EVENT_WRITE)
            while data:
                self.check()
                if selector.select(0.1):
                    try:
                        count = os.write(self.process.stdin.fileno(), data)
                    except BrokenPipeError as exc:
                        raise Problem(422, "MODEL_FAILED", "模型在接收预测数据时退出") from exc
                    data = data[count:]
        result = self.receive()
        values = np.asarray(result.get("values"), dtype=float)
        if values.shape != (len(array),) or not np.isfinite(values).all():
            raise Problem(422, "MODEL_OUTPUT", "预测输出不完整或含非有限值")
        return values

    def close(self):
        if self.process is not None:
            for pipe in (self.process.stdin, self.process.stdout, self.process.stderr):
                if pipe is not None:
                    pipe.close()
        if self.created:
            removed = subprocess.run(
                [self.docker, "rm", "--force", self.name],
                capture_output=True,
                timeout=15,
                check=False,
            )
            if removed.returncode and b"No such container" not in removed.stderr:
                raise Problem(503, "MODEL_CLEANUP", "仅本次模型容器未能清理")
        if self.process is not None:
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        if self.directory is not None:
            shutil.rmtree(self.directory)

    def __exit__(self, *exception):
        self.close()
