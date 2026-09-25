"""New model authorization and automatic table binding, independent of old approvals."""

import pytest
from coastmas_next.store import Problem


def test_runtime_has_no_execution_qualification_without_new_approval(workspace, tmp_path):
    from coastmas_next.models import ModelRegistry, Release

    settings, store, client, project = workspace
    release = Release(
        model_id="ppci_mcdc",
        image="sha256:" + "a" * 64,
        source_sha256="b" * 64,
        proof_sha256="c" * 64,
        package="PPCI",
        version="0.1.5",
    )
    registry = ModelRegistry(store, [release])
    actor = client.get("/api/session").json()["id"]
    assert registry.catalog(actor, project)[0]["approved"] is False
    with pytest.raises(Problem, match="运行包"):
        registry.require(actor, project, "ppci_mcdc")
    registry.approve(actor, project, release.model_id, release.digest)
    assert registry.require(actor, project, "ppci_mcdc")["release"]["image"] == release.image
    changed = Release(**{**release.model_dump(), "proof_sha256": "d" * 64})
    assert ModelRegistry(store, [changed]).catalog(actor, project)[0]["approved"] is False
    viewer = store.sign_in("viewer@example.test", "safe-password-for-tests")[0]
    with pytest.raises(Problem):
        registry.approve(
            store.authenticate(viewer)["id"], project, release.model_id, release.digest
        )


def test_table_binding_preserves_identity_and_physical_conversion(workspace):
    from coastmas_next.models import table_frame

    settings, _, client, project = workspace
    response = client.post(
        f"/api/projects/{project}/assets",
        files={"file": ("measure.csv", b"id,x,y\n001,0,2\n002,100,4\n003,200,6\n004,300,8\n")},
    ).json()
    asset = response["asset"]
    mapping = [
        {
            "asset_id": asset["id"],
            "field": "table/id",
            "role": "identity",
            "unit": None,
            "concept": None,
        },
        {
            "asset_id": asset["id"],
            "field": "table/x",
            "role": "feature",
            "unit": "cm",
            "concept": "measured length",
        },
        {
            "asset_id": asset["id"],
            "field": "table/y",
            "role": "response",
            "unit": "m",
            "concept": "response length",
        },
    ]
    manifest = {
        "assets": [asset],
        "draft": {
            "purpose": "regression",
            "mapping": mapping,
            "options": {"standardize": False},
            "selection": [{"asset_id": asset["id"], "revision": 1}],
        },
    }
    frame = table_frame(settings, manifest)
    assert frame.row_ids == ("001", "002", "003", "004")
    assert frame.values[0] == (0.0,)
    assert frame.response == (2.0, 4.0, 6.0, 8.0)
    assert frame.response_unit == "m"
    assert frame.observation_scope == "all_joint_valid_cells"
    assert frame.joint_valid_cells == 4
    manifest["draft"]["mapping"][1]["field"] = "table/not_present"
    with pytest.raises(Problem):
        table_frame(settings, manifest)


def test_missing_and_duplicate_observations_are_not_silently_dropped(workspace):
    from coastmas_next.models import table_frame

    settings, _, client, project = workspace
    a = client.post(
        f"/api/projects/{project}/assets",
        files={"file": ("bad.csv", b"id,x\n01,1\n01,2\n03,\n04,4\n")},
    ).json()["asset"]
    m = {
        "assets": [a],
        "draft": {
            "purpose": "cluster",
            "mapping": [
                {"asset_id": a["id"], "field": "table/id", "role": "identity"},
                {
                    "asset_id": a["id"],
                    "field": "table/x",
                    "role": "feature",
                    "unit": "m",
                    "concept": "length",
                },
            ],
            "options": {"standardize": False},
        },
    }
    with pytest.raises(Problem):
        table_frame(settings, m)
