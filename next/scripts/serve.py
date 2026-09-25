"""Run the new API and worker together; own processes only, never replace a server."""

import argparse
import json
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / ".state/settings.json")
    parser.add_argument("--port", type=int, default=58010)
    args = parser.parse_args()
    if not args.config.is_file():
        raise SystemExit("Initialize the new namespace first")
    configured = json.loads(args.config.read_text())
    web_root = Path(configured.get("web_root", ROOT / "web/dist")).resolve()
    if not (web_root / "index.html").is_file():
        raise SystemExit("Configured frontend build is missing; build next/web first")
    if not 1024 <= args.port <= 65535:
        raise SystemExit("Use a local unprivileged port")
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", args.port))
        except OSError:
            raise SystemExit("Port is occupied; existing service left untouched") from None
    stopping = False

    def stop(_signal, _frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    processes = []
    try:
        for role in ("api", "worker"):
            command = [
                sys.executable,
                str(ROOT / "scripts/dev.py"),
                role,
                "--config",
                str(args.config.resolve()),
            ]
            if role == "api":
                command += ["--port", str(args.port)]
            processes.append(subprocess.Popen(command, cwd=ROOT.parent))
        print(f"CoastMAS new workspace: http://127.0.0.1:{args.port}/", flush=True)
        while not stopping and all(process.poll() is None for process in processes):
            time.sleep(0.25)
        if not stopping:
            raise SystemExit("A new-version process exited; inspect its error output")
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                # Do not escalate to a forced kill of a scientific task.
                print(
                    f"Waiting for owned process {process.pid} to finish its current operation",
                    file=sys.stderr,
                )
                process.wait()


if __name__ == "__main__":
    main()
