import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from coastmas.adapters.http import HTTPAdapter, RemoteEndpoint
from coastmas.adapters.runtime import RunRequest
from coastmas.core.errors import CoastMASError


@pytest.fixture
def endpoint():
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if self.path == "/redirect":
                self.send_response(302)
                self.send_header("Location", "http://169.254.169.254/latest/meta-data/")
                self.end_headers()
                return
            if self.path == "/slow":
                time.sleep(0.5)
            payload = json.dumps({"result": request["inputs"]["value"] + 1}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            try:
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError):
                # Client timeout is the behavior under test.
                return

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    thread.join(2)
    server.server_close()


def test_real_registered_http_model_executes_and_cleans_up(endpoint, tmp_path):
    adapter = HTTPAdapter({"remote": RemoteEndpoint(endpoint + "/model", allow_private=True)})
    result = adapter.run(RunRequest("remote", {"value": 41}, {}, tmp_path, 5))
    assert result.outputs == {"result": 42}
    assert not list(tmp_path.iterdir())


def test_private_addresses_and_redirects_are_not_implicitly_trusted(endpoint, tmp_path):
    request = RunRequest("remote", {"value": 1}, {}, tmp_path, 5)
    with pytest.raises(CoastMASError, match="private"):
        HTTPAdapter({"remote": RemoteEndpoint(endpoint + "/model")}).run(request)
    with pytest.raises(CoastMASError, match="redirect"):
        HTTPAdapter({"remote": RemoteEndpoint(endpoint + "/redirect", allow_private=True)}).run(
            request
        )
    assert not list(tmp_path.iterdir())


def test_remote_deadline_and_output_budget_are_enforced(endpoint, tmp_path):
    with pytest.raises(CoastMASError, match="deadline|timeout"):
        HTTPAdapter({"remote": RemoteEndpoint(endpoint + "/slow", allow_private=True)}).run(
            RunRequest("remote", {"value": 1}, {}, tmp_path, 0.1)
        )
    with pytest.raises(CoastMASError, match="budget"):
        HTTPAdapter(
            {"remote": RemoteEndpoint(endpoint + "/model", allow_private=True)}, max_output_bytes=4
        ).run(RunRequest("remote", {"value": 1}, {}, tmp_path, 5))
    assert not list(tmp_path.iterdir())
