"""W01/W02 contracts on an actual isolated PostgreSQL database, not SQLite substitutes."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from coastmas_next.v1.contracts import ContractError, validate_contract
from coastmas_next.v1.foundation import Foundation, VersionConflict


def empty_method():
    return {
        "schema_version": "coastmas.method-draft/1.0",
        "name": "", "revision": 0, "task_type": "assessment", "indicators": [],
        "estimator_or_evaluator_ref": None, "basis_text": None, "basis_refs": [],
    }


def test_contract_partial_draft_and_rejected_types():
    validate_contract("MethodDraft", empty_method())
    for patch in [{"revision": True}, {"basis_text": 42}, {"token": "not-a-real-secret"}]:
        with pytest.raises(ContractError):
            validate_contract("MethodDraft", {**empty_method(), **patch})
    with pytest.raises(ContractError):
        validate_contract("MethodDraft", {**empty_method(), "revision": float("nan")})
    with pytest.raises(ContractError):
        validate_contract("MethodVersion", empty_method())


def test_postgres_role_and_migration_guards(database):
    with database.context() as c:
        assert c.scalar(text("SELECT extversion FROM pg_extension WHERE extname='postgis'"))
        row = c.execute(text("SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user")).one()
        assert tuple(row) == (False, False)
        assert c.scalar(text("SELECT count(*) FROM pg_tables WHERE schemaname='public' AND tableowner=current_user")) == 0
        policies = c.execute(text("SELECT relrowsecurity,relforcerowsecurity FROM pg_class WHERE relname='resource_revisions'")).one()
        assert tuple(policies) == (True, True)


def test_project_topic_task_boundaries_and_no_admin_data_override(foundation, actors):
    owner, outsider, _ = actors
    p = foundation.create_project(owner, "项目甲")
    q = foundation.create_project(outsider, "项目乙")
    topic = foundation.create_topic(owner, p["id"], "海岸研究", "")
    for kind in ["assessment", "simulation", "planning", "comparison"]:
        task = foundation.create_task(owner, p["id"], topic["id"], kind, "", "研究")
        assert task["task_type"] == kind and task["topic_id"] == topic["id"]
    with pytest.raises(ContractError):
        foundation.create_task(owner, p["id"], topic["id"], "ahp", "", "错误类型")
    with pytest.raises(ContractError):
        foundation.create_task(outsider, q["id"], topic["id"], "assessment", "", "跨项目")
    with foundation.db.context(outsider) as c:
        assert c.scalar(text("SELECT count(*) FROM research_topics WHERE project_id=:p"), {"p": p["id"]}) == 0
        assert c.scalar(text("SELECT count(*) FROM resources WHERE project_id=:p"), {"p": p["id"]}) == 0
    with foundation.db.context() as c:
        assert c.scalar(text("SELECT nullif(current_setting('coastmas.actor',true),'')")) is None
        assert c.scalar(text("SELECT count(*) FROM resources")) == 0


def test_resource_cas_and_immutable_versions(foundation, actors):
    owner, outsider, viewer = actors
    project = foundation.create_project(owner, "版本测试")
    foundation.add_member(owner, project["id"], viewer, "VIEWER")
    resource = foundation.create_resource(owner, project["id"], "method", "方案", "MethodDraft", empty_method())
    resource_id = resource["resource_id"]
    saved = foundation.save_draft(owner, resource_id, 0, "MethodDraft", {**empty_method(), "basis_text": "尚未完整"})
    assert saved["revision"] == 1
    with pytest.raises(VersionConflict):
        foundation.save_draft(owner, resource_id, 0, "MethodDraft", empty_method())
    with pytest.raises(ContractError):
        foundation.freeze(owner, resource_id, 1, "MethodVersion")
    assert foundation.read_draft(owner, resource_id)["body"]["basis_text"] == "尚未完整"
    with pytest.raises(PermissionError):
        foundation.save_draft(viewer, resource_id, 1, "MethodDraft", empty_method())
    with pytest.raises(LookupError):
        foundation.read_draft(outsider, resource_id)
    # Task snapshots accept scientifically incomplete drafts but are never marked runnable.
    topic = foundation.create_topic(owner, project["id"], "主题", "")
    task = foundation.create_task(owner, project["id"], topic["id"], "assessment", "", "空研究")
    first = foundation.freeze(owner, task["resource_id"], 0, "TaskDraft")
    assert first["version_no"] == 1 and first["spec"]["inputs"] == []
    with foundation.db.context(owner) as c:
        with pytest.raises(DBAPIError):
            c.execute(text("UPDATE resource_revisions SET spec='{}' WHERE id=:id"), {"id": first["id"]})
    with foundation.db.context(owner) as c:
        assert c.scalar(text("SELECT spec_hash FROM resource_revisions WHERE id=:id"), {"id": first["id"]}) == first["spec_hash"]


def test_concurrent_draft_writers_only_one_wins(foundation, actors):
    owner = actors[0]
    p = foundation.create_project(owner, "并发")
    resource = foundation.create_resource(owner, p["id"], "method", "方法", "MethodDraft", empty_method())
    def save(label):
        try:
            return foundation.save_draft(owner, resource["resource_id"], 0, "MethodDraft", {**empty_method(), "name": label})["revision"]
        except VersionConflict:
            return "conflict"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(save, ["A", "B"]))
    assert sorted(map(str, results)) == ["1", "conflict"]


def test_foreign_project_revision_and_kind_cannot_be_forged(foundation, actors):
    owner = actors[0]
    p = foundation.create_project(owner, "来源")
    q = foundation.create_project(owner, "其他项目")
    topic = foundation.create_topic(owner, p["id"], "主题", "")
    task = foundation.create_task(owner, p["id"], topic["id"], "assessment", "", "任务")
    revision = foundation.freeze(owner, task["resource_id"], 0, "TaskDraft")
    with foundation.db.context(owner) as c:
        with pytest.raises(DBAPIError):
            c.execute(text("INSERT INTO resource_revisions(id,resource_id,project_id,version_no,schema_name,spec_hash,spec,created_by) VALUES (:id,:r,:p,2,'TaskDraft','bad','{}',:a)"), {"id":uuid4(), "r":task["resource_id"], "p":q["id"], "a":owner})
    with pytest.raises(ContractError):
        foundation.resolve_ref(owner, p["id"], {"resource_id":str(task["resource_id"]), "revision_id":str(revision["id"]), "kind":"method"})
