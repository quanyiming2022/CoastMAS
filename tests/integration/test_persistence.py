"""Real PostgreSQL tests; unavailable services are failures, never mock passes."""

from uuid import uuid4

import pytest
from sqlalchemy import update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from coastmas.core.errors import CoastMASError
from coastmas.persistence.resources import create_resource, read_resource, update_resource
from coastmas.persistence.schema import ResourceVersion


def test_resource_permissions_and_immutable_versions(engine, actors):
    owner, viewer, outsider, project = actors
    identifier = str(uuid4())
    with Session(engine) as session, session.begin():
        first = create_resource(
            session,
            user_id=owner,
            project_id=project,
            kind="scene",
            identifier=identifier,
            name="first",
            spec={"id": identifier, "version": 1, "value": 1},
        )
        assert first.version == 1
    with Session(engine) as session, session.begin():
        second = update_resource(
            session,
            user_id=owner,
            identifier=identifier,
            expected_version=1,
            spec={"id": identifier, "version": 2, "value": 2},
        )
        assert second.version == 2
        assert (
            read_resource(session, user_id=viewer, identifier=identifier, version=1).spec["value"]
            == 1
        )
    with Session(engine) as session, session.begin():
        with pytest.raises(CoastMASError, match="permission"):
            read_resource(session, user_id=outsider, identifier=identifier)
        with pytest.raises(CoastMASError, match="permission"):
            update_resource(
                session,
                user_id=viewer,
                identifier=identifier,
                expected_version=2,
                spec={"id": identifier, "version": 3},
            )
        with pytest.raises(CoastMASError, match="conflict"):
            update_resource(
                session,
                user_id=owner,
                identifier=identifier,
                expected_version=1,
                spec={"id": identifier, "version": 2},
            )
    with pytest.raises(DBAPIError):
        with Session(engine) as session, session.begin():
            session.execute(
                update(ResourceVersion)
                .where(ResourceVersion.resource_id == identifier)
                .values(spec={"tampered": True})
            )


def test_foreign_key_rejects_orphan_versions(engine):
    with pytest.raises(IntegrityError):
        with Session(engine) as session, session.begin():
            session.add(
                ResourceVersion(
                    resource_id="missing",
                    version=1,
                    spec={},
                    checksum="a" * 64,
                    created_by=str(uuid4()),
                )
            )
