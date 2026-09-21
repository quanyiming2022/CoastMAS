"""Authenticated collaboration HTTP flow against real PostgreSQL."""

from uuid import uuid4

from sqlalchemy.orm import Session

from coastmas.persistence.schema import User
from tests.factories import scene


def test_proposal_api_revisions_comparison_comments_and_review_permissions(authenticated, engine):
    client, csrf, project, owner = authenticated
    headers = {"X-CSRF-Token": csrf}
    assert (
        client.get("/api/v1/collaboration/access", params={"project_id": project}).json()["role"]
        == "RESEARCHER"
    )
    selected = scene(id=str(uuid4()))
    assert (
        client.post(
            "/api/v1/scenes",
            headers=headers,
            json={"project_id": project, "spec": selected.model_dump(mode="json")},
        ).status_code
        == 201
    )
    proposal = {
        "id": str(uuid4()),
        "name": "SYNTHETIC coastal proposal",
        "version": 1,
        "scene": {"id": selected.id, "version": 1},
        "rationale": "Explicit hard budget",
        "objectives": [{"objective_id": "benefit", "name": "Benefit", "weight": 1}],
        "constraints": [
            {"constraint_id": "cost", "metric": "cost", "unit": "dimensionless", "maximum": 10}
        ],
    }
    created = client.post(
        "/api/v1/proposals", headers=headers, json={"project_id": project, "spec": proposal}
    )
    assert created.status_code == 201, created.text
    base = "/api/v1/proposals/" + proposal["id"]
    assert created.json()["spec"]["author_id"] == owner
    assert (
        client.get("/api/v1/proposals", params={"project_id": project}).json()[0]["resource_id"]
        == proposal["id"]
    )
    spoof = client.post(
        "/api/v1/proposals",
        headers=headers,
        json={"project_id": project, "spec": {**proposal, "author_id": "forged"}},
    )
    assert spoof.status_code == 422
    compared = client.post(
        "/api/v1/proposals/compare",
        headers=headers,
        json={"project_id": project, "proposals": [{"id": proposal["id"], "version": 1}]},
    )
    assert compared.status_code == 200, compared.text
    assert compared.json()["constraints"]["policy_decision"] is False
    assert compared.json()["proposals"][0]["objectives"][0]["weight"] == 1
    note = {
        "proposal_version": 1,
        "content": "Actual human opinion, not a policy decision.",
        "idempotency_key": str(uuid4()),
    }
    comment = client.post(base + "/comments", headers=headers, json=note)
    assert comment.status_code == 201, comment.text
    assert comment.json()["spec"]["author_id"] == owner
    assert client.post(base + "/comments", headers=headers, json=note).json() == comment.json()
    assert (
        client.post(
            base + "/comments", headers=headers, json={**note, "content": "different"}
        ).status_code
        == 409
    )
    assert len(client.get(base + "/comments", params={"version": 1}).json()) == 1
    assert (
        client.post(base + "/submit", headers=headers, json={"expected_version": 1}).status_code
        == 200
    )
    denied = client.post(
        base + "/review",
        headers=headers,
        json={"expected_version": 2, "conclusion": "REVIEWED", "rationale": "Not a manager"},
    )
    assert denied.status_code == 403
    assert [x["version"] for x in client.get(base + "/versions").json()] == [1, 2]
    with Session(engine) as session, session.begin():
        session.get(User, owner).is_admin = True
    # Even an administrator cannot claim independent review of their own proposal.
    assert (
        client.post(
            base + "/review",
            headers=headers,
            json={"expected_version": 2, "conclusion": "REVIEWED", "rationale": "Self review"},
        ).status_code
        == 403
    )
    assert (
        client.put(
            base + "/publication", headers=headers, json={"expected_version": 2, "published": True}
        ).status_code
        == 422
    )
    assert (
        client.put(
            "/api/v1/collaboration/scenes/" + selected.id + "/publication",
            headers=headers,
            json={"expected_version": 1, "published": True},
        ).status_code
        == 200
    )


def test_public_http_visibility_and_revision_unpublishing(authenticated, engine, actors):
    from coastmas.core.collaboration import ProposalDraft
    from coastmas.persistence.collaboration import review_proposal, save_proposal, submit_proposal
    from coastmas.persistence.resources import create_resource
    from coastmas.persistence.schema import Membership, Resource

    client, csrf, project, public = authenticated
    public, owner, manager, _ = actors
    headers = {"X-CSRF-Token": csrf}
    with Session(engine) as session, session.begin():
        session.add(Membership(project_id=project, user_id=manager, role="MANAGER"))
        session.get(Membership, (project, owner)).role = "RESEARCHER"
        selected = scene(id=str(uuid4()))
        create_resource(
            session,
            user_id=owner,
            project_id=project,
            kind="scene",
            identifier=selected.id,
            name=selected.name,
            spec=selected.model_dump(mode="json"),
        )
        proposal = ProposalDraft(
            id=str(uuid4()),
            name="Published synthetic proposal",
            version=1,
            scene={"id": selected.id, "version": 1},
            rationale="Recorded rationale",
            objectives=({"objective_id": "habitat", "name": "Habitat", "weight": 1},),
            constraints=(),
        )
        save_proposal(session, user_id=owner, project_id=project, draft=proposal)
        submit_proposal(session, user_id=owner, identifier=proposal.id, expected_version=1)
        review_proposal(
            session,
            user_id=manager,
            identifier=proposal.id,
            expected_version=2,
            conclusion="REVIEWED",
            rationale="Independent review",
        )
        session.get(Resource, proposal.id).published = True
        session.get(Resource, selected.id).published = True
        session.get(Membership, (project, public)).role = "PUBLIC"
    available = client.get("/api/v1/collaboration/scenes", params={"project_id": project})
    assert available.status_code == 200, available.text
    assert available.json()[0]["resource_id"] == selected.id
    # Public participation cannot alter another author's proposal.
    assert client.get("/api/v1/proposals/" + proposal.id).status_code == 200
    comment = client.post(
        "/api/v1/proposals/" + proposal.id + "/comments",
        headers=headers,
        json={"proposal_version": 3, "content": "Public opinion", "idempotency_key": str(uuid4())},
    )
    assert comment.status_code == 201, comment.text
    assert comment.json()["spec"]["author_role"] == "PUBLIC"
    assert (
        client.post(
            "/api/v1/proposals/" + proposal.id + "/submit",
            headers=headers,
            json={"expected_version": 3},
        ).status_code
        == 403
    )
    with Session(engine) as session, session.begin():
        # Simulate an actual authorized author revision, without spoofing HTTP identity.
        revised = proposal.model_copy(update={"version": 4, "rationale": "New assumptions"})
        save_proposal(session, user_id=owner, project_id=project, draft=revised, expected_version=3)
        assert session.get(Resource, proposal.id).published is False
    assert client.get("/api/v1/proposals/" + proposal.id).status_code == 403
    assert (
        client.get(
            "/api/v1/proposals/" + proposal.id + "/comments", params={"version": 3}
        ).status_code
        == 403
    )
    assert client.get("/api/v1/proposals", params={"project_id": project}).json() == []
