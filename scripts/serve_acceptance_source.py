"""Local synthetic HTTP source used by real connector browser acceptance."""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CONTENT = b"height,label\n0,zero\n2,two\n"


class SyntheticSource(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path != "/observations.csv":
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Length", str(len(CONTENT)))
        self.send_header("X-CoastMAS-Data", "SYNTHETIC")
        self.end_headers()
        self.wfile.write(CONTENT)

    def log_message(self, format: str, *args: object) -> None:
        return


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=58090)
    arguments = parser.parse_args()
    with ThreadingHTTPServer(("127.0.0.1", arguments.port), SyntheticSource) as server:
        print("SYNTHETIC acceptance source listening on local port", server.server_port, flush=True)
        server.serve_forever()
