"""Administrator-registered sources, imported as bounded immutable file snapshots.

No caller-supplied SQL or redirect is executed. Network/DB work runs in a killable
process; the parent receives bytes or a sanitized error, never credentials.
"""

import base64
import csv
import http.client
import io
import ipaddress
import socket
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import JsonValue
from sqlalchemy import Text, case, cast, column, create_engine, func, literal, select, table, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.sql import quoted_name

from coastmas.adapters.http import PinnedConnection
from coastmas.adapters.runtime import PythonFunctionAdapter, RunRequest
from coastmas.core.errors import CoastMASError


@dataclass(frozen=True)
class HTTPSource:
    url: str = field(repr=False)
    allow_private: bool = False
    headers: dict[str, str] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class PostgreSQLSource:
    dsn: str = field(repr=False)
    schema: str
    table: str
    columns: tuple[str, ...]
    order_by: tuple[str, ...]


Source = HTTPSource | PostgreSQLSource


def http_snapshot(source: HTTPSource, max_bytes: int) -> bytes:
    address = urlsplit(source.url)
    if (
        address.scheme not in {"http", "https"}
        or not address.hostname
        or address.username
        or address.password
        or address.fragment
    ):
        raise CoastMASError("SOURCE_CONFIGURATION", "registered URL is invalid")
    port = address.port or (443 if address.scheme == "https" else 80)
    addresses = sorted(
        {
            str(item[4][0])
            for item in socket.getaddrinfo(address.hostname, port, type=socket.SOCK_STREAM)
        }
    )
    if not addresses:
        raise CoastMASError("SOURCE_CONFIGURATION", "source has no address")
    for value in addresses:
        numeric = ipaddress.ip_address(value)
        if not numeric.is_global and not source.allow_private:
            raise CoastMASError(
                "SOURCE_CONFIGURATION", "private source requires administrator registration"
            )
        if address.scheme == "http" and (numeric.is_global or not source.allow_private):
            raise CoastMASError("SOURCE_CONFIGURATION", "public sources require HTTPS")
    headers = {"Accept-Encoding": "identity"}
    for name, value in source.headers.items():
        if name.lower() not in {"authorization", "x-api-key"} or any(
            char in value for char in "\r\n"
        ):
            raise CoastMASError("SOURCE_CONFIGURATION", "unapproved source header")
        headers[name] = value
    connection = PinnedConnection(address.hostname, port, addresses[0], address.scheme == "https")
    try:
        path = address.path or "/"
        if address.query:
            path += "?" + address.query
        connection.request("GET", path, headers=headers)
        response = connection.getresponse()
        if 300 <= response.status < 400:
            raise CoastMASError("SOURCE_REDIRECT", "source redirect rejected")
        if not 200 <= response.status < 300:
            raise CoastMASError("SOURCE_STATUS", f"source returned HTTP {response.status}")
        if response.headers.get("Content-Encoding", "identity").lower() != "identity":
            raise CoastMASError("SOURCE_FORMAT", "compressed HTTP transport is not accepted")
        content = response.read(max_bytes + 1)
        if len(content) > max_bytes:
            raise CoastMASError("SOURCE_LIMIT", "source byte budget exceeded")
        return content
    finally:
        connection.close()


def postgres_snapshot(source: PostgreSQLSource, max_bytes: int, max_rows: int) -> bytes:
    if (
        not source.dsn.startswith("postgresql+psycopg://")
        or not source.columns
        or len(source.columns) > 64
        or len(set(source.columns)) != len(source.columns)
        or not source.order_by
        or not set(source.order_by).issubset(source.columns)
    ):
        raise CoastMASError(
            "SOURCE_CONFIGURATION", "database source requires registered columns and ordering"
        )
    relation = table(
        quoted_name(source.table, True),
        *(column(quoted_name(name, True)) for name in source.columns),
        schema=quoted_name(source.schema, True),
    )
    # Do not transfer an oversized database value into the Python process. PostgreSQL
    # measures requested text fields first; an oversize marker makes the whole import fail.
    size = sum(
        (func.coalesce(func.octet_length(cast(item, Text)), 0) for item in relation.c),
        start=literal(0),
    )
    oversized = size > max_bytes
    query = (
        select(oversized, *(case((oversized, None), else_=cast(item, Text)) for item in relation.c))
        .order_by(*(relation.c[name] for name in source.order_by))
        .limit(max_rows + 1)
    )
    output = bytearray()

    def append(values: tuple[str | None, ...]) -> None:
        buffer = io.StringIO(newline="")
        csv.writer(buffer, lineterminator="\n").writerow(values)
        encoded = buffer.getvalue().encode("utf-8")
        if len(output) + len(encoded) > max_bytes:
            raise CoastMASError("SOURCE_LIMIT", "source byte budget exceeded")
        output.extend(encoded)

    append(source.columns)
    engine = create_engine(source.dsn, hide_parameters=True, connect_args={"connect_timeout": 5})
    try:
        with engine.begin() as connection:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            connection.execute(text("SET LOCAL statement_timeout = 5000"))
            connection.execute(text("SET LOCAL TIME ZONE 'UTC'"))
            result = connection.execution_options(stream_results=True, max_row_buffer=100).execute(
                query
            )
            keys: set[tuple[str | None, ...]] = set()
            key_indexes = [source.columns.index(name) for name in source.order_by]
            for index, row in enumerate(result):
                if index >= max_rows:
                    raise CoastMASError("SOURCE_LIMIT", "source row budget exceeded")
                if row[0]:
                    raise CoastMASError("SOURCE_LIMIT", "database value exceeds byte budget")
                values = tuple(None if value is None else str(value) for value in row[1:])
                key = tuple(values[position] for position in key_indexes)
                if None in key or key in keys:
                    raise CoastMASError(
                        "SOURCE_ORDER", "database ordering must have unique non-null keys"
                    )
                keys.add(key)
                append(values)
        return bytes(output)
    finally:
        engine.dispose()


def _fetch(
    source: Source,
    max_bytes: int,
    max_rows: int,
    inputs: dict[str, JsonValue],
    parameters: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    try:
        content = (
            http_snapshot(source, max_bytes)
            if isinstance(source, HTTPSource)
            else postgres_snapshot(source, max_bytes, max_rows)
        )
        return {"content": base64.b64encode(content).decode("ascii")}
    except CoastMASError as error:
        return {"error_code": error.code, "message": error.message}
    except (OSError, ValueError, http.client.HTTPException, SQLAlchemyError):
        return {
            "error_code": "SOURCE_UNAVAILABLE",
            "message": "registered source could not be read",
        }


def fetch_source(
    source: Source,
    *,
    work_root: Path,
    max_bytes: int = 64 * 1024 * 1024,
    max_rows: int = 100000,
    timeout_seconds: float = 30,
) -> bytes:
    if (
        not 1 <= max_bytes <= 64 * 1024 * 1024
        or not 1 <= max_rows <= 100000
        or not 0 < timeout_seconds <= 30
    ):
        raise CoastMASError("SOURCE_CONFIGURATION", "source budgets are outside allowed bounds")
    adapter = PythonFunctionAdapter(
        {"fetch": partial(_fetch, source, max_bytes, max_rows)},
        max_output_bytes=2 * max_bytes + 4096,
    )
    result = adapter.run(
        RunRequest(
            handler="fetch",
            inputs={},
            parameters={},
            work_root=work_root,
            timeout_seconds=timeout_seconds,
        )
    ).outputs
    if isinstance(result.get("error_code"), str) and isinstance(result.get("message"), str):
        raise CoastMASError(str(result["error_code"]), str(result["message"]))
    encoded = result.get("content")
    if not isinstance(encoded, str):
        raise CoastMASError("SOURCE_FORMAT", "source connector returned invalid content")
    return base64.b64decode(encoded, validate=True)
