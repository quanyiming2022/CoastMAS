"""Real immutable proposal versions, human review and restricted participation."""

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from coastmas.core.collaboration import ProposalDraft
from coastmas.core.errors import CoastMASError
from coastmas.persistence.collaboration import review_proposal, save_proposal, submit_proposal
from coastmas.persistence.resources import create_resource, read_resource
from coastmas.persistence.schema import Membership, Resource, ResourceDependency
from tests.factories import scene


def setup_scene(session, owner, project, published=False):
    spec = scene(id=str(uuid4()))
    create_resource(
        session,
        user_id=owner,
        project_id=project,
        kind="scene",
        identifier=spec.id,
        name=spec.name,
        spec=spec.model_dump(mode="json"),
    )
    session.get(Resource, spec.id).published = published
    session.flush()
    return spec


def draft(scene_id, **changes):
    return ProposalDraft.model_validate(
        dict(
            id=str(uuid4()),
            name="SYNTHETIC proposal",
            version=1,
            scene={"id": scene_id, "version": 1},
            rationale="Explicit stakeholder objectives",
            objectives=[{"objective_id": "habitat", "name": "Habitat", "weight": 1}],
            constraints=[{"constraint_id": "area", "metric": "area", "unit": "m^2", "minimum": 0}],
            **changes,
        )
    )


def test_human_review_version_history_and_dependencies(engine, actors):
    owner, viewer, manager, project = actors
    with Session(engine) as session, session.begin():
        session.add(Membership(project_id=project, user_id=manager, role="MANAGER"))
        selected = setup_scene(session, owner, project)
        proposal = draft(selected.id)
        first = save_proposal(session, user_id=owner, project_id=project, draft=proposal)
        assert first.spec["author_id"] == owner and first.spec["status"] == "DRAFT"
        with pytest.raises(CoastMASError):
            submit_proposal(session, user_id=viewer, identifier=proposal.id, expected_version=1)
        submitted = submit_proposal(
            session, user_id=owner, identifier=proposal.id, expected_version=1
        )
        assert submitted.version == 2 and submitted.spec["status"] == "SUBMITTED"
        with pytest.raises(CoastMASError):
            review_proposal(
                session,
                user_id=owner,
                identifier=proposal.id,
                expected_version=2,
                conclusion="REVIEWED",
                rationale="Cannot review oneself",
            )
        reviewed = review_proposal(
            session,
            user_id=manager,
            identifier=proposal.id,
            expected_version=2,
            conclusion="REVIEWED",
            rationale="Human review of evidence",
        )
        assert reviewed.spec["review"]["reviewer_id"] == manager
        assert reviewed.spec["author_id"] == owner
        assert (
            read_resource(session, user_id=viewer, identifier=proposal.id, version=1).spec["status"]
            == "DRAFT"
        )
        revision = proposal.model_copy(
            update={"version": 4, "rationale": "New scientific assumptions"}
        )
        revised = save_proposal(
            session, user_id=owner, project_id=project, draft=revision, expected_version=3
        )
        assert revised.spec["status"] == "DRAFT" and revised.spec["review"] is None
        dependencies = session.scalars(
            select(ResourceDependency).where(ResourceDependency.source_id == proposal.id)
        ).all()
        assert {row.source_version for row in dependencies} == {1, 2, 3, 4}
        with pytest.raises(CoastMASError):
            save_proposal(
                session, user_id=owner, project_id=project, draft=revision, expected_version=3
            )


def test_public_participation_does_not_grant_general_write_or_private_access(engine, actors):
    owner, public, outsider, project = actors
    with Session(engine) as session, session.begin():
        session.get(Membership, (project, public)).role = "PUBLIC"
        private_scene = setup_scene(session, owner, project)
        with pytest.raises(CoastMASError):
            save_proposal(
                session, user_id=public, project_id=project, draft=draft(private_scene.id)
            )
        shared = setup_scene(session, owner, project, published=True)
        own = save_proposal(session, user_id=public, project_id=project, draft=draft(shared.id))
        assert own.spec["author_role"] == "PUBLIC"
        assert read_resource(session, user_id=public, identifier=own.resource_id).version == 1
        other = save_proposal(session, user_id=owner, project_id=project, draft=draft(shared.id))
        for actor, identifier in [(public, other.resource_id), (outsider, own.resource_id)]:
            with pytest.raises(CoastMASError):
                read_resource(session, user_id=actor, identifier=identifier)
        with pytest.raises(CoastMASError):
            setup_scene(session, public, project)
        with pytest.raises(CoastMASError):
            save_proposal(
                session,
                user_id=public,
                project_id=project,
                draft=ProposalDraft.model_validate(
                    {
                        key: (2 if key == "version" else value)
                        for key, value in other.spec.items()
                        if key in ProposalDraft.model_fields
                    }
                ),
                expected_version=1,
            )


def test_private_evidence_and_scene_revisions_remain_guarded(engine, actors):
    from coastmas.persistence.resources import update_resource

    owner, public, outsider, project = actors
    with Session(engine) as session, session.begin():
        session.get(Membership, (project, public)).role = "PUBLIC"
        selected = setup_scene(session, owner, project, published=True)
        invalid = draft(selected.id).model_copy(update={"evidence_results": (str(uuid4()),)})
        with pytest.raises(CoastMASError, match="actual successful result"):
            save_proposal(session, user_id=owner, project_id=project, draft=invalid)
        with pytest.raises(CoastMASError, match="permission"):
            save_proposal(session, user_id=public, project_id=project, draft=invalid)
        revised = selected.model_copy(
            update={"version": 2, "management_goal": "Unpublished new conditions"}
        )
        update_resource(
            session,
            user_id=owner,
            identifier=selected.id,
            expected_version=1,
            spec=revised.model_dump(mode="json"),
        )
        assert session.get(Resource, selected.id).published is False
        with pytest.raises(CoastMASError):
            read_resource(session, user_id=public, identifier=selected.id)


def test_author_reassigned_viewer_retains_read_access_but_cannot_revise(engine, actors):
    owner, viewer, outsider, project = actors
    with Session(engine) as session, session.begin():
        selected = setup_scene(session, owner, project)
        proposal = draft(selected.id)
        save_proposal(session, user_id=owner, project_id=project, draft=proposal)
        session.get(Membership, (project, owner)).role = "VIEWER"
        assert read_resource(session, user_id=owner, identifier=proposal.id).version == 1
        with pytest.raises(CoastMASError):
            save_proposal(
                session,
                user_id=owner,
                project_id=project,
                draft=proposal.model_copy(update={"version": 2}),
                expected_version=1,
            )


def test_result_reference_matches_full_pinned_scene_manifest(engine, actors):
    """Result-reference validation fixture; not evidence of a scientific model run."""
    from coastmas.persistence.jobs import claim_job, publish_result, submit_job
    from coastmas.persistence.schema import ResultBundle

    owner, viewer, outsider, project = actors
    with Session(engine) as session, session.begin():
        selected = setup_scene(session, owner, project)
        job = submit_job(
            session,
            user_id=owner,
            project_id=project,
            idempotency_key=str(uuid4()),
            manifest={"scene": selected.model_dump(mode="json"), "test_fixture": True},
        )
        token = claim_job(session, job.id, lease_seconds=60)
        assert token is not None
        assert publish_result(
            session, job_id=job.id, worker_token=token, manifest={"test_fixture": True}
        )
        result = session.scalar(select(ResultBundle).where(ResultBundle.job_id == job.id))
        proposal = draft(selected.id).model_copy(update={"evidence_results": (result.id,)})
        saved = save_proposal(session, user_id=owner, project_id=project, draft=proposal)
        assert saved.spec["evidence_results"] == [result.id]
        different = setup_scene(session, owner, project)
        with pytest.raises(CoastMASError, match="pinned scene"):
            save_proposal(
                session,
                user_id=owner,
                project_id=project,
                draft=draft(different.id).model_copy(update={"evidence_results": (result.id,)}),
            )
