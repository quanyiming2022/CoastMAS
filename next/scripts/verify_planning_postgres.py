"""Disposable isolated schema test; never connects the application to superuser credentials."""

import json, os, secrets, shutil, subprocess, tempfile
import argparse, re
from datetime import datetime, UTC
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "next/src"), str(ROOT / "next/vendor")]
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from coastmas_next.app import create_app
from coastmas_next.config import Settings

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument("--evidence-label",default=datetime.now(UTC).strftime("%Y%m%dT%H%M%S"))
label=parser.parse_args().evidence_label
if not re.fullmatch(r"[A-Za-z0-9-]{1,40}",label):
    raise SystemExit("Invalid evidence label")
log=ROOT / f"next/artifacts/master-20260925/planning-postgres-{label}.log"
if log.exists():
    raise SystemExit("Evidence already exists; use a new label")
env = {}
for line in (ROOT / ".env").read_text().splitlines():
    if "=" in line and not line.startswith("#"):
        key, value = line.split("=", 1)
        env[key] = value
url = URL.create(
    "postgresql+psycopg",
    username=env.get("POSTGRES_USER", "coastmas"),
    password=env["POSTGRES_PASSWORD"],
    host="127.0.0.1",
    port=int(env.get("POSTGRES_PORT", "55432")),
    database="postgres",
)
suffix = secrets.token_hex(4)
database = "coastmas_next_planning_test_" + suffix
role = "coastmas_next_test_" + suffix
password = secrets.token_urlsafe(32)
admin = create_engine(url, isolation_level="AUTOCOMMIT")
with admin.connect() as c:
    c.execute(text(f'CREATE DATABASE "{database}"'))
    # Identifiers are generated hex; the secret is parameter-quoted by psycopg.
    from psycopg import sql

    c.connection.driver_connection.execute(
        sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD {}").format(
            sql.Identifier(role), sql.Literal(password)
        )
    )
directory = Path(tempfile.mkdtemp(prefix="coastmas-planning-pg-"))
settings = Settings(
    database_url=url.set(database=database).render_as_string(hide_password=False),
    storage_root=directory / "migration-objects",
)
store = create_app(settings).state.store
store.initialize()
with store.engine.begin() as c:
    c.execute(text(f'GRANT USAGE ON SCHEMA public TO "{role}"'))
    c.execute(text(f'GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO "{role}"'))
    c.execute(text(f'GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO "{role}"'))
store.engine.dispose()
app_url = url.set(database=database, username=role, password=password).render_as_string(
    hide_password=False
)
config = directory / "private-test-settings.json"
config.write_text(json.dumps({"database_url": app_url, "storage_root": str(directory / "objects")}))
config.chmod(0o600)
(directory / "conftest.py").write_text("""
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select,text
from coastmas_next.app import create_app
from coastmas_next.config import Settings
from coastmas_next.store import accounts
@pytest.fixture
def workspace():
    data=json.loads((Path(__file__).parent/'private-test-settings.json').read_text())
    settings=Settings(database_url=data['database_url'],storage_root=Path(data['storage_root']))
    settings.storage_root.mkdir(parents=True,exist_ok=True)
    app=create_app(settings);store=app.state.store
    with store.engine.connect() as c:
        assert c.execute(text('SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user')).one()==(False,False)
        assert c.scalar(text("SELECT count(*) FROM pg_tables WHERE schemaname='public' AND tableowner=current_user"))==0
        admin=c.scalar(select(accounts.c.id).where(accounts.c.email=='admin@example.test'))
        viewer=c.scalar(select(accounts.c.id).where(accounts.c.email=='viewer@example.test'))
    if not admin:admin=store.create_account('admin@example.test','safe-password-for-tests',system_admin=True)
    if not viewer:viewer=store.create_account('viewer@example.test','safe-password-for-tests')
    project=store.create_project(admin,'Isolated PostgreSQL planning test')
    store.set_member(admin,project,viewer,'viewer')
    client=TestClient(app)
    response=client.post('/api/session',json={'email':'admin@example.test','password':'safe-password-for-tests'})
    assert response.status_code==200
    client.headers['X-CSRF-Token']=response.json()['csrf']
    yield settings,store,client,project
    client.close();store.engine.dispose()
""")
shutil.copyfile(
    ROOT / "next/tests/test_planning_versions.py", directory / "test_planning_versions.py"
)
shutil.copyfile(ROOT / "next/tests/test_planning_units.py", directory / "test_planning_units.py")
process_env = os.environ.copy()
process_env["PYTHONPATH"] = str(ROOT / "next/src") + os.pathsep + str(ROOT / "next/vendor")
with log.open("w") as output:
    result = subprocess.run(
        [
            str(ROOT / "next/.venv/bin/python"),
            "-m",
            "pytest",
            str(directory / "test_planning_versions.py"),
            str(directory / "test_planning_units.py"),
            "-q",
            "--rootdir",
            str(directory),
        ],
        env=process_env,
        cwd=directory,
        stdout=output,
        stderr=subprocess.STDOUT,
    )
log.write_text(log.read_text().replace(password, "[REDACTED isolated test credential]"))
evidence = {
    "database": database,
    "role": role,
    "api_role_superuser": False,
    "api_role_bypassrls": False,
    "api_role_owns_tables": False,
    "rls_policies": "NOT_IMPLEMENTED",
    "test_exit_code": result.returncode,
    "log": str(log.relative_to(ROOT / "next")),
    "scope": "Planning versions and unit artifacts; not W01 complete acceptance",
}
(ROOT / f"next/artifacts/master-20260925/planning-postgres-{label}-evidence.json").write_text(
    json.dumps(evidence, indent=2)
)
admin.dispose()
print(
    json.dumps(
        {
            "exit_code": result.returncode,
            "database": database,
            "evidence": f"planning-postgres-{label}-evidence.json",
        }
    )
)
raise SystemExit(result.returncode)
