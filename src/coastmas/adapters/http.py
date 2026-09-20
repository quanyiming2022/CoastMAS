"""Registered HTTP models in killable isolated Python processes.

DNS is resolved once and the actual connection uses that pinned IP. Redirects,
proxies and user-supplied URLs are not followed. HTTPS certificate validation
still uses the original host. Explicit private services are maintainer-only
configuration. A timeout/cancel never automatically retries a remote model:
the remote completion state can be unknown even though the local process stops.
"""

import http.client
import ipaddress
import json
import socket
import ssl
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import JsonValue

from coastmas.adapters.runtime import (
    OUTPUT_SCHEMA,
    AdapterResult,
    Handler,
    PythonFunctionAdapter,
    RunRequest,
)
from coastmas.core.errors import CoastMASError


@dataclass(frozen=True)
class RemoteEndpoint:
    url: str
    allow_private: bool = False
    headers: dict[str, str] = field(default_factory=dict, repr=False)


class PinnedConnection(http.client.HTTPConnection):
    def __init__(self, host: str, port: int, address: str, secure: bool):
        super().__init__(host, port, timeout=30)
        self.address = address
        self.secure = secure

    def connect(self) -> None:
        self.sock = socket.create_connection((self.address, self.port), timeout=self.timeout)
        if self.secure:
            self.sock = ssl.create_default_context().wrap_socket(
                self.sock, server_hostname=self.host
            )


def remote_call(
    endpoint: RemoteEndpoint,
    max_bytes: int,
    inputs: dict[str, JsonValue],
    parameters: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    connection: PinnedConnection | None = None
    try:
        address = urlsplit(endpoint.url)
        if (
            address.scheme not in ("http", "https")
            or not address.hostname
            or address.username
            or address.password
            or address.fragment
        ):
            raise CoastMASError("HTTP_CONFIGURATION", "registered endpoint URL is invalid")
        port = address.port or (443 if address.scheme == "https" else 80)
        candidates = socket.getaddrinfo(address.hostname, port, type=socket.SOCK_STREAM)
        addresses = sorted({str(record[4][0]) for record in candidates})
        if not addresses:
            raise CoastMASError("HTTP_CONFIGURATION", "registered endpoint has no address")
        for value in addresses:
            numeric = ipaddress.ip_address(value)
            if not numeric.is_global and not endpoint.allow_private:
                raise CoastMASError(
                    "HTTP_CONFIGURATION",
                    "private endpoint requires explicit administrator registration",
                )
            if address.scheme == "http" and (numeric.is_global or not endpoint.allow_private):
                raise CoastMASError("HTTP_CONFIGURATION", "public model endpoints require HTTPS")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        for name, value in endpoint.headers.items():
            if name.lower() not in ("authorization", "x-api-key") or any(
                character in value for character in "\r\n"
            ):
                raise CoastMASError("HTTP_CONFIGURATION", "unapproved registered HTTP header")
            headers[name] = value
        payload = json.dumps({"inputs": inputs, "parameters": parameters}, allow_nan=False).encode()
        if len(payload) > max_bytes:
            raise CoastMASError("HTTP_LIMIT", "HTTP request exceeds byte budget")
        connection = PinnedConnection(
            address.hostname, port, addresses[0], address.scheme == "https"
        )
        path = address.path or "/"
        if address.query:
            path += "?" + address.query
        connection.request("POST", path, body=payload, headers=headers)
        response = connection.getresponse()
        if 300 <= response.status < 400:
            raise CoastMASError("HTTP_REDIRECT", "model redirect rejected")
        if response.status < 200 or response.status >= 300:
            raise CoastMASError("HTTP_STATUS", f"model returned HTTP {response.status}")
        if response.headers.get_content_type() != "application/json":
            raise CoastMASError("MODEL_OUTPUT_ERROR", "HTTP model must return JSON")
        raw = response.read(max_bytes + 1)
        if len(raw) > max_bytes:
            raise CoastMASError("HTTP_LIMIT", "HTTP response exceeds byte budget")
        parsed = OUTPUT_SCHEMA.validate_json(raw)
        json.dumps(parsed, allow_nan=False)
        return {"payload": parsed}
    except CoastMASError as exc:
        return {"transport_error": {"code": exc.code, "message": exc.message}}
    except (OSError, http.client.HTTPException):
        return {
            "transport_error": {
                "code": "REMOTE_STATUS_UNKNOWN",
                "message": "remote connection failed; completion state unknown",
            }
        }
    except ValueError:
        return {
            "transport_error": {
                "code": "MODEL_OUTPUT_ERROR",
                "message": "remote output is not finite valid JSON",
            }
        }
    finally:
        if connection is not None:
            connection.close()


class HTTPAdapter(PythonFunctionAdapter):
    def __init__(self, endpoints: dict[str, RemoteEndpoint], max_output_bytes: int = 1048576):
        handlers: dict[str, Handler] = {
            name: partial(remote_call, endpoint, max_output_bytes)
            for name, endpoint in endpoints.items()
        }
        super().__init__(handlers, max_output_bytes=max_output_bytes + 2048)

    def execute(self, request: RunRequest, directory: Path) -> tuple[bytes, int, float]:
        try:
            return super().execute(request, directory)
        except CoastMASError as exc:
            if exc.code in {"TIMEOUT", "CANCELLED"}:
                raise CoastMASError(
                    "REMOTE_STATUS_UNKNOWN",
                    "local deadline or cancellation stopped waiting; "
                    "remote completion state unknown",
                ) from exc
            raise

    def collect(self, output: bytes, exit_code: int, elapsed: float) -> AdapterResult:
        envelope = super().collect(output, exit_code, elapsed).outputs
        failure = envelope.get("transport_error")
        if (
            isinstance(failure, dict)
            and isinstance(failure.get("code"), str)
            and isinstance(failure.get("message"), str)
        ):
            raise CoastMASError(str(failure["code"]), str(failure["message"]))
        payload = envelope.get("payload")
        if not isinstance(payload, dict):
            raise CoastMASError("MODEL_OUTPUT_ERROR", "invalid HTTP transport envelope")
        return AdapterResult(payload, exit_code, elapsed)
