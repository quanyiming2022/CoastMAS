from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from coastmas.core.errors import CoastMASError
from coastmas.persistence.lifecycle import archive_resource, resource_history
from coastmas.persistence.resources import create_resource, read_resource
from coastmas.persistence.schema import Resource, ResourceDependency
from tests.factories import asset, model, workflow


def test_workflow_dependencies_protect_referenced_versions_from_archive(engine, actors):
    user, _, _, project = actors
    suffix = uuid4().hex
    source = model(id="m-" + suffix)
    data = asset(id="d-" + suffix)
    raw = workflow().model_dump(mode="json")
    raw["id"] = "w-" + suffix
    raw["nodes"][0]["model_id"] = source.id
    raw["input_bindings"][0]["source"]["id"] = data.id
    flow = workflow(**raw)
    with Session(engine) as session, session.begin():
        for kind, value in [("model", source), ("data", data), ("workflow", flow)]:
            create_resource(
                session,
                user_id=user,
                project_id=project,
                kind=kind,
                identifier=value.id,
                name=value.name,
                spec=value.model_dump(mode="json"),
            )
        assert session.get(ResourceDependency, (flow.id, 1, source.id, 1)) is not None
        assert session.get(ResourceDependency, (flow.id, 1, data.id, 1)) is not None
        with pytest.raises(CoastMASError, match="referenced"):
            archive_resource(session, user_id=user, identifier=source.id)


def test_unused_resource_archive_preserves_history_and_checks_permissions(engine, actors):
    user, viewer, _, project = actors
    identifier = uuid4().hex
    with Session(engine) as session, session.begin():
        create_resource(
            session,
            user_id=user,
            project_id=project,
            kind="model",
            identifier=identifier,
            name="unused",
            spec={"id": identifier, "version": 1, "name": "unused"},
        )
        with pytest.raises(CoastMASError):
            archive_resource(session, user_id=viewer, identifier=identifier)
        archive_resource(session, user_id=user, identifier=identifier)
        resource = session.get(Resource, identifier)
        assert resource.archived and not resource.enabled
        assert (
            read_resource(session, user_id=user, identifier=identifier, version=1).spec["name"]
            == "unused"
        )
        assert [
            revision.version
            for revision in resource_history(session, user_id=user, identifier=identifier)
        ] == [1]


def test_workflow_cannot_reference_unavailable_or_foreign_project_data(engine, actors):
    user, _, _, project = actors
    flow = workflow(id=uuid4().hex)
    with Session(engine) as session, session.begin():
        with pytest.raises(CoastMASError, match="reference"):
            create_resource(
                session,
                user_id=user,
                project_id=project,
                kind="workflow",
                identifier=flow.id,
                name=flow.name,
                spec=flow.model_dump(mode="json"),
            )
        assert session.get(Resource, flow.id) is None


def test_archive_cannot_race_new_workflow_reference(engine, actors, monkeypatch):
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor

    import coastmas.persistence.resources as resources

    user, _, _, project = actors
    suffix = uuid4().hex
    source = model(id="m-" + suffix)
    data = asset(id="d-" + suffix)
    raw = workflow().model_dump(mode="json")
    raw["id"] = "w-" + suffix
    raw["nodes"][0]["model_id"] = source.id
    raw["input_bindings"][0]["source"]["id"] = data.id
    flow = workflow(**raw)
    with Session(engine) as session, session.begin():
        for kind, value in [("model", source), ("data", data)]:
            create_resource(
                session,
                user_id=user,
                project_id=project,
                kind=kind,
                identifier=value.id,
                name=value.name,
                spec=value.model_dump(mode="json"),
            )
    ready = threading.Event()
    release = threading.Event()
    original = resources.workflow_references

    def hold_reference(*args, **kwargs):
        result = original(*args, **kwargs)
        ready.set()
        assert release.wait(5)
        return result

    monkeypatch.setattr(resources, "workflow_references", hold_reference)

    def create():
        with Session(engine) as session, session.begin():
            create_resource(
                session,
                user_id=user,
                project_id=project,
                kind="workflow",
                identifier=flow.id,
                name=flow.name,
                spec=flow.model_dump(mode="json"),
            )

    def archive():
        try:
            with Session(engine) as session, session.begin():
                archive_resource(session, user_id=user, identifier=source.id)
        except CoastMASError as exc:
            return exc.code
        return "ARCHIVED"

    with ThreadPoolExecutor(max_workers=2) as pool:
        writer = pool.submit(create)
        assert ready.wait(5)
        archiver = pool.submit(archive)
        try:
            time.sleep(0.15)
            assert not archiver.done(), "archive must wait for the in-flight reference transaction"
        finally:
            release.set()
        writer.result(timeout=5)
        assert archiver.result(timeout=5) == "DEPENDENCY_CONFLICT"


def test_update_rechecks_version_after_lock_even_with_cached_orm_identity(engine, actors):
    from coastmas.persistence.resources import update_resource

    user, _, _, project = actors
    identifier = uuid4().hex
    with Session(engine) as session, session.begin():
        create_resource(
            session,
            user_id=user,
            project_id=project,
            kind="model",
            identifier=identifier,
            name="original",
            spec={"id": identifier, "version": 1, "name": "original"},
        )
    with Session(engine) as stale:
        held = stale.get(Resource, identifier)
        assert held.current_version == 1
        with Session(engine) as fresh, fresh.begin():
            update_resource(
                fresh,
                user_id=user,
                identifier=identifier,
                expected_version=1,
                spec={"id": identifier, "version": 2, "name": "new"},
            )
        with pytest.raises(CoastMASError, match="version conflict"):
            update_resource(
                stale,
                user_id=user,
                identifier=identifier,
                expected_version=1,
                spec={"id": identifier, "version": 2, "name": "stale"},
            )


def test_permission_revocation_invalidates_cached_membership(engine, actors):
    from sqlalchemy import delete

    from coastmas.persistence.resources import require_permission
    from coastmas.persistence.schema import Membership

    user, _, _, project = actors
    with Session(engine) as stale:
        held = stale.get(Membership, (project, user))
        assert held.role == "RESEARCHER"
        with Session(engine) as fresh, fresh.begin():
            fresh.execute(
                delete(Membership).where(
                    Membership.project_id == project, Membership.user_id == user
                )
            )
        with pytest.raises(CoastMASError, match="permission"):
            require_permission(stale, user, project, "read")


def test_invalid_update_does_not_stage_partial_version_when_error_is_caught(engine, actors):
    from coastmas.persistence.resources import update_resource

    user, _, _, project = actors
    identifier = uuid4().hex
    with Session(engine) as session, session.begin():
        create_resource(
            session,
            user_id=user,
            project_id=project,
            kind="model",
            identifier=identifier,
            name="original",
            spec={"id": identifier, "version": 1, "name": "original"},
        )
        with pytest.raises(CoastMASError, match="boolean"):
            update_resource(
                session,
                user_id=user,
                identifier=identifier,
                expected_version=1,
                spec={"id": identifier, "version": 2, "name": "changed", "enabled": "false"},
            )
    with Session(engine) as session:
        revision = read_resource(session, user_id=user, identifier=identifier)
        assert revision.version == 1
        assert session.get(Resource, identifier).name == "original"
