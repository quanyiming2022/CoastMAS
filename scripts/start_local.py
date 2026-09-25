"""Start this existing macOS installation without reseeding or stopping services."""

import fcntl
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener

ROOT = Path(__file__).resolve().parents[1]
URL = "http://127.0.0.1:58000"
SERVICES = ("worker", "beat", "api")


@contextmanager
def start_lock(directory: Path) -> Iterator[None]:
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (directory / "startup.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("另一个启动脚本正在运行，请等待它完成。") from exc
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def check_prerequisites(root: Path) -> None:
    for path, message in (
        (".venv/bin/python", "缺少项目 Python 环境，请先按 docs/web-runtime.md 安装。"),
        (".env", "缺少私有 .env 配置；请恢复本机配置，不要使用他人密码。"),
        ("apps/web/dist/index.html", "缺少前端构建，请先运行 npm --prefix apps/web run build。"),
    ):
        if not (root / path).is_file():
            raise RuntimeError(message)
    for command in ("docker", "ps", "lsof"):
        if not shutil.which(command):
            raise RuntimeError(f"缺少 {command} 命令，请先安装并配置 PATH。")


def process_directory(pid: int) -> Path:
    result = subprocess.run(
        ["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    for line in result.stdout.splitlines():
        if line.startswith("n/"):
            return Path(line[1:]).resolve()
    raise RuntimeError(f"无法核实进程 {pid} 的项目目录，暂不启动重复服务。")


def discover_services(root: Path) -> dict[str, int]:
    output = subprocess.check_output(
        ["ps", "-ax", "-o", "pid=", "-o", "command="], text=True, timeout=10
    )
    found: dict[str, int] = {}
    for line in output.splitlines():
        match = re.match(r"\s*(\d+)\s+.*(?:^|\s)-m\s+coastmas\s+(api|worker|beat)\s*$", line)
        if not match:
            continue
        pid, service = int(match[1]), match[2]
        if process_directory(pid) != root.resolve():
            continue
        if service in found:
            raise RuntimeError(f"检测到本项目多个 {service} 进程，请先核查；脚本不会停止它们。")
        found[service] = pid
    return found


def port_in_use() -> bool:
    with socket.socket() as listener:
        try:
            listener.bind(("127.0.0.1", 58000))
            return False
        except OSError:
            return True


def ensure_infrastructure(root: Path, logs: Path) -> None:
    # Private output can contain connection diagnostics; never echo it into chat.
    with (logs / "infrastructure.log").open("ab") as output:
        result = subprocess.run(
            [
                "docker",
                "compose",
                "--env-file",
                str(root / ".env"),
                "-f",
                str(root / "docker-compose.infra.yml"),
                "up",
                "-d",
                "--no-recreate",
                "--wait",
            ],
            cwd=root,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
            timeout=120,
            check=False,
        )
    if result.returncode:
        raise RuntimeError(
            f"基础服务启动失败，请确认 Docker Desktop 已运行。日志：{logs / 'infrastructure.log'}"
        )


def spawn_service(root: Path, service: str, logs: Path) -> subprocess.Popen[bytes]:
    environment = os.environ.copy()
    environment.update(COASTMAS_HOST="127.0.0.1", COASTMAS_PORT="58000", PYTHONUNBUFFERED="1")
    with (logs / f"{service}.log").open("ab") as output:
        return subprocess.Popen(
            [str(root / ".venv/bin/python"), "-m", "coastmas", service],
            cwd=root,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
        )


def application_ready() -> bool:
    opener = build_opener(ProxyHandler({}))
    try:
        with opener.open(URL + "/health/ready", timeout=5) as response:
            report = json.load(response)
        if report.get("status") != "ready" or report.get("dependencies") != {
            "database": "ready",
            "object_storage": "ready",
            "queue": "ready",
        }:
            return False
        with opener.open(URL + "/", timeout=5) as response:
            return response.status == 200 and "text/html" in response.headers.get(
                "Content-Type", ""
            )
    except (OSError, URLError, ValueError):
        return False


def wait_for_application(processes: dict[str, subprocess.Popen[bytes]]) -> None:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        for service, process in processes.items():
            if process.poll() is not None:
                raise RuntimeError(f"{service} 启动后退出，请检查对应日志。")
        if application_ready():
            return
        time.sleep(1)
    raise RuntimeError("60 秒内网页或依赖未就绪，请检查日志；已启动进程保留，不自动停止任务。")


def start(root: Path = ROOT) -> dict[str, int]:
    os.umask(0o077)
    check_prerequisites(root)
    logs = root / "artifacts/runtime/start-local"
    with start_lock(logs):
        existing = discover_services(root)
        if port_in_use() and "api" not in existing:
            raise RuntimeError("58000 已被无法确认属于本项目的程序占用；不会结束占用进程。")
        print("检查基础服务；保留已有容器和数据…", flush=True)
        ensure_infrastructure(root, logs)
        processes: dict[str, subprocess.Popen[bytes]] = {}
        for service in SERVICES:
            if service in existing:
                print(f"复用 {service}（PID {existing[service]}）", flush=True)
            else:
                processes[service] = spawn_service(root, service, logs)
                existing[service] = processes[service].pid
                print(f"启动 {service}（PID {existing[service]}）", flush=True)
        (logs / "services.json").write_text(json.dumps(existing, indent=2) + "\n")
        # Catch early worker/beat startup failures even when an older API is already ready.
        if processes:
            time.sleep(3)
        wait_for_application(processes)
        for service, pid in existing.items():
            try:
                os.kill(pid, 0)  # Existence check only; this sends no termination signal.
            except ProcessLookupError as exc:
                raise RuntimeError(f"{service} 已退出，请检查日志。") from exc
        print(f"网页及依赖已就绪：{URL}\n服务日志：{logs}", flush=True)
        return existing


def main() -> int:
    try:
        start()
    except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
        print(f"启动未完成：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
