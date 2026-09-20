"""Build the pinned MinIO security source for Linux using a verified local Go toolchain.

The loopback relay uses TLS to the official module proxy; Go still verifies go.sum
and the signed checksum database. It works around a diagnosed Go-only transport
failure without changing host/Docker network settings or allowing arbitrary URLs.
"""

import hashlib
import json
import logging
import os
import platform
import shutil
import subprocess
import tarfile
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "artifacts/runtime/minio-native-build"
COMMIT = "9e49d5e7a648f00e26f2246f4dc28e6b07f8c84a"
SOURCE_SHA = "45521908307306e925c98d629e1c17d78c8b72b6ee242b1bfb1409f7d8ee5841"
GO_SHA = "a012b25b571bd0138a03dcd25375ceba866fe5ca822f426d2c66a4de56fd3f4b"
TARGET = "arm64"


DOWNLOAD_SLOTS = threading.BoundedSemaphore(16)


class ModuleServer(ThreadingHTTPServer):
    request_queue_size = 256


class OfficialModuleRelay(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        logging.debug(format, *args)

    def do_GET(self) -> None:
        with DOWNLOAD_SLOTS:
            self.forward_module()

    def forward_module(self) -> None:
        if not self.path.startswith("/") or self.path.startswith("//") or len(self.path) > 4096:
            self.send_error(400, "invalid module path")
            return
        try:
            with urlopen("https://proxy.golang.org" + self.path, timeout=60) as response:
                size = response.headers.get("Content-Length")
                if size is not None and int(size) > 256 * 1024 * 1024:
                    self.send_error(502, "module archive exceeds download budget")
                    return
                self.send_response(response.status)
                if size is not None:
                    self.send_header("Content-Length", size)
                self.end_headers()
                count = 0
                while chunk := response.read(1024 * 1024):
                    count += len(chunk)
                    if count > 256 * 1024 * 1024:
                        raise ValueError("module archive exceeds download budget")
                    self.wfile.write(chunk)
        except HTTPError as exc:
            self.send_error(exc.code, "official module proxy rejected request")
        except (OSError, ValueError) as exc:
            logging.error("Module relay transport failure: %s", type(exc).__name__)
            self.close_connection = True


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def build(source: Path) -> None:
    if digest(BUILD / "go.tar.gz") != GO_SHA or digest(BUILD / "minio.tar.gz") != SOURCE_SHA:
        raise SystemExit("Pinned toolchain or source archive checksum mismatch")
    go = BUILD / "go/bin/go"
    image = BUILD / "image"
    image.mkdir(exist_ok=True)
    server = ModuleServer(("127.0.0.1", 0), OfficialModuleRelay)
    relay = threading.Thread(target=server.serve_forever, daemon=True)
    relay.start()
    environment = {
        **os.environ,
        "GOTOOLCHAIN": "local",
        "CGO_ENABLED": "0",
        "GOOS": "linux",
        "GOARCH": TARGET,
        "GOMODCACHE": str(BUILD / "module-cache"),
        "GOCACHE": str(BUILD / "build-cache"),
        "GOPROXY": f"http://127.0.0.1:{server.server_port}",
        "GOSUMDB": "sum.golang.org",
        "GONOSUMDB": "",
        "GOPRIVATE": "",
        "GONOPROXY": "",
    }
    flags = " ".join(
        [
            "-s -w",
            "-X github.com/minio/minio/cmd.Version=2025-10-15T17:29:55Z",
            "-X github.com/minio/minio/cmd.ReleaseTag=RELEASE.2025-10-15T17-29-55Z.coastmas-source",
            f"-X github.com/minio/minio/cmd.CommitID={COMMIT}",
            f"-X github.com/minio/minio/cmd.ShortCommitID={COMMIT[:12]}",
            "-X github.com/minio/minio/cmd.CopyrightYear=2025",
        ]
    )
    try:
        with (ROOT / "artifacts/logs/minio-native-relay-compile.log").open("w") as log:
            subprocess.run(
                [
                    str(go),
                    "build",
                    "-mod=readonly",
                    "-trimpath",
                    "-buildvcs=false",
                    "-ldflags",
                    flags,
                    "-o",
                    str(image / "minio"),
                    ".",
                ],
                cwd=source,
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=True,
                timeout=1800,
            )
            subprocess.run(
                [
                    str(go),
                    "build",
                    "-trimpath",
                    "-ldflags",
                    "-s -w",
                    "-o",
                    str(image / "health"),
                    str(ROOT / "deploy/minio/health.go"),
                ],
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=True,
                timeout=120,
            )
    finally:
        server.shutdown()
        server.server_close()
        relay.join(timeout=5)
    import certifi

    shutil.copyfile(certifi.where(), image / "ca-certificates.crt")
    shutil.copyfile(source / "LICENSE", image / "LICENSE")
    shutil.copyfile(BUILD / "minio.tar.gz", image / "source.tar.gz")
    for directory in ("data", "tmp"):
        (image / directory).mkdir(exist_ok=True)
    receipt = {
        "source_commit": COMMIT,
        "source_archive_sha256": SOURCE_SHA,
        "go_version": "go1.26.8",
        "go_archive_sha256": GO_SHA,
        "target": "linux/" + TARGET,
        "module_verification": "go.sum and signed sum.golang.org; no checksum bypass",
        "files": {path.name: digest(path) for path in image.iterdir() if path.is_file()},
    }
    (ROOT / "artifacts/evidence/minio-native-build.json").write_text(
        json.dumps(receipt, indent=2) + "\n"
    )
    print("Native MinIO compilation passed; checksums recorded.")


def pinned_download(url: str, target: Path, checksum: str) -> None:
    if target.exists():
        if digest(target) != checksum:
            raise SystemExit("Existing build input has an unexpected checksum")
        return
    temporary = target.with_suffix(".download")
    with urlopen(url, timeout=60) as response, temporary.open("wb") as stream:
        size = 0
        while chunk := response.read(1024 * 1024):
            size += len(chunk)
            if size > 200_000_000:
                raise RuntimeError("Build input exceeds download budget")
            stream.write(chunk)
    if digest(temporary) != checksum:
        raise SystemExit("Downloaded build input checksum mismatch")
    temporary.replace(target)


def main() -> None:
    # This desktop recovery recipe produces a portable Linux/ARM64 runtime image.
    # Its build toolchain is intentionally specific to this verified Apple Silicon host.
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise SystemExit("This pinned build recipe requires an Apple Silicon macOS host")
    BUILD.mkdir(parents=True, exist_ok=True)
    pinned_download("https://go.dev/dl/go1.26.8.darwin-arm64.tar.gz", BUILD / "go.tar.gz", GO_SHA)
    pinned_download(
        "https://codeload.github.com/minio/minio/tar.gz/" + COMMIT,
        BUILD / "minio.tar.gz",
        SOURCE_SHA,
    )
    with tarfile.open(BUILD / "go.tar.gz") as archive:
        archive.extractall(BUILD, filter="data")
    with tempfile.TemporaryDirectory(prefix="verified-source-", dir=BUILD) as temporary:
        with tarfile.open(BUILD / "minio.tar.gz") as archive:
            archive.extractall(temporary, filter="data")
        build(Path(temporary) / ("minio-" + COMMIT))


if __name__ == "__main__":
    main()
