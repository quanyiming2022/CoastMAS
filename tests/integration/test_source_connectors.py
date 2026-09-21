import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from sqlalchemy import text

from coastmas.adapters.source_connectors import HTTPSource, PostgreSQLSource, fetch_source
from coastmas.core.errors import CoastMASError


@pytest.fixture
def source_server():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/redirect":
                self.send_response(302)
                self.send_header("Location", "/data")
                self.end_headers()
                return
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"height,label\n0,zero\n2,two\n")

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_registered_http_reads_exact_bytes_and_enforces_private_scope(source_server, tmp_path):
    source = HTTPSource(url=source_server + "/data", allow_private=True)
    assert fetch_source(source, work_root=tmp_path) == b"height,label\n0,zero\n2,two\n"
    with pytest.raises(CoastMASError, match="private"):
        fetch_source(HTTPSource(url=source_server + "/data"), work_root=tmp_path)
    with pytest.raises(CoastMASError, match="redirect"):
        fetch_source(
            HTTPSource(url=source_server + "/redirect", allow_private=True), work_root=tmp_path
        )
    with pytest.raises(CoastMASError, match="budget"):
        fetch_source(source, work_root=tmp_path, max_bytes=8)


def test_registered_postgres_exports_ordered_snapshot_without_credentials(engine, tmp_path):
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE source_measurements "
                "(id integer primary key, height numeric, label text)"
            )
        )
        connection.execute(
            text("INSERT INTO source_measurements VALUES (2, 2.25, 'two'), (1, 0, 'zero')")
        )
    source = PostgreSQLSource(
        dsn=engine.url.render_as_string(hide_password=False),
        schema="public",
        table="source_measurements",
        columns=("id", "height", "label"),
        order_by=("id",),
    )
    output = fetch_source(source, work_root=tmp_path)
    assert output.decode() == "id,height,label\n1,0,zero\n2,2.25,two\n"
    assert "password" not in repr(source).lower()
    with pytest.raises(CoastMASError, match="row budget"):
        fetch_source(source, work_root=tmp_path, max_rows=1)
    bad = PostgreSQLSource(
        dsn=source.dsn,
        schema="public",
        table="source_measurements; DROP TABLE source_measurements",
        columns=("id",),
        order_by=("id",),
    )
    with pytest.raises(CoastMASError):
        fetch_source(bad, work_root=tmp_path)
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM source_measurements")) == 2


def test_postgres_source_cannot_execute_writes_or_transfer_oversized_values(engine, tmp_path):
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE source_guard (id integer primary key, value text)"))
        connection.execute(text("INSERT INTO source_guard VALUES (1, repeat('x', 1000))"))
        connection.execute(
            text("""CREATE FUNCTION source_write_attempt() RETURNS integer
            LANGUAGE plpgsql AS $$ BEGIN
            INSERT INTO source_guard VALUES (2, 'changed'); RETURN 2; END; $$""")
        )
        connection.execute(
            text("CREATE VIEW source_write_view AS SELECT source_write_attempt() AS id")
        )
    dsn = engine.url.render_as_string(hide_password=False)
    source = PostgreSQLSource(
        dsn=dsn, schema="public", table="source_guard", columns=("id", "value"), order_by=("id",)
    )
    with pytest.raises(CoastMASError, match="byte budget"):
        fetch_source(source, work_root=tmp_path, max_bytes=32)
    attempted_write = PostgreSQLSource(
        dsn=dsn, schema="public", table="source_write_view", columns=("id",), order_by=("id",)
    )
    with pytest.raises(CoastMASError, match="could not be read"):
        fetch_source(attempted_write, work_root=tmp_path)
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM source_guard")) == 1


def test_source_errors_hide_credentials_and_reject_unbounded_configuration(source_server, tmp_path):
    secret = "credential-never-printed"
    source = HTTPSource(
        url=source_server + "/data",
        allow_private=True,
        headers={"Authorization": "Bearer " + secret + "\r\nInjected: x"},
    )
    with pytest.raises(CoastMASError) as failure:
        fetch_source(source, work_root=tmp_path)
    assert secret not in str(failure.value)
    assert secret not in repr(source)
    with pytest.raises(CoastMASError):
        fetch_source(source, work_root=tmp_path, max_rows=0)
    with pytest.raises(CoastMASError):
        fetch_source(
            HTTPSource(url=source_server + "/data", allow_private=True),
            work_root=tmp_path,
            timeout_seconds=31,
        )
