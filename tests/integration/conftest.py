"""Real PostgreSQL tests; unavailable services are failures, never mock passes."""

from uuid import uuid4

import boto3
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from coastmas.adapters.storage import S3ArtifactStore, local_storage_settings
from coastmas.persistence.database import local_database_url
from coastmas.persistence.schema import Membership, Project, User


@pytest.fixture(scope="module")
def engine():
    database_name = "coastmas_test_" + uuid4().hex
    administrative = create_engine(local_database_url(), isolation_level="AUTOCOMMIT")
    with administrative.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{database_name}"'))
    temporary = create_engine(local_database_url(database_name))
    config = Config("alembic.ini")
    config.attributes["engine"] = temporary
    config.attributes["allow_test_downgrade"] = True
    try:
        command.upgrade(config, "head")
        command.downgrade(config, "base")
        command.upgrade(config, "head")
        yield temporary
    finally:
        temporary.dispose()
        with administrative.connect() as connection:
            connection.execute(text(f'DROP DATABASE "{database_name}" WITH (FORCE)'))
        administrative.dispose()


@pytest.fixture
def actors(engine):
    user_id = str(uuid4())
    viewer_id = str(uuid4())
    outsider_id = str(uuid4())
    project_id = str(uuid4())
    with Session(engine) as session, session.begin():
        session.add_all(
            [
                User(
                    id=user_id, email=user_id + "@test.invalid", password_hash="unusable-test-hash"
                ),
                User(
                    id=viewer_id,
                    email=viewer_id + "@test.invalid",
                    password_hash="unusable-test-hash",
                ),
                User(
                    id=outsider_id,
                    email=outsider_id + "@test.invalid",
                    password_hash="unusable-test-hash",
                ),
            ]
        )
        session.flush()
        session.add(Project(id=project_id, name="Test project", owner_id=user_id))
        session.flush()
        session.add_all(
            [
                Membership(project_id=project_id, user_id=user_id, role="RESEARCHER"),
                Membership(project_id=project_id, user_id=viewer_id, role="VIEWER"),
            ]
        )
    return user_id, viewer_id, outsider_id, project_id


@pytest.fixture
def storage():
    settings = local_storage_settings()
    bucket = "coastmas-test-" + uuid4().hex
    store = S3ArtifactStore(settings, bucket=bucket)
    store.ensure_bucket()
    yield store
    client = boto3.client(
        "s3",
        endpoint_url=settings.endpoint,
        aws_access_key_id=settings.access_key,
        aws_secret_access_key=settings.secret_key,
        region_name="us-east-1",
    )
    response = client.list_objects_v2(Bucket=bucket)
    for item in response.get("Contents", []):
        client.delete_object(Bucket=bucket, Key=item["Key"])
    client.delete_bucket(Bucket=bucket)
