"""Global runtime definitions and a single read-only audit query."""

import hashlib
import shutil

from fastapi import APIRouter, Query, Request
from sqlalchemy import func, select

from .administration import require_admin
from .store import accounts, audit, projects, tasks

ACTION_NAMES = {
    "create_account": "创建账号",
    "create_project": "创建项目",
    "create_task": "创建研究",
    "save_draft": "保存研究配置",
    "attach_inputs": "加入研究资料",
    "ingest_asset": "导入资料",
    "replay_ingest": "恢复资料导入",
    "set_member": "修改项目成员",
    "remove_member": "移除项目成员",
    "grant_local_source": "授权项目来源",
    "revoke_local_source": "撤销项目来源",
    "reset_password": "重置密码",
    "create_import": "创建导入批次",
    "approve_template": "认可方法版本",
}


def router(store):
    routes = APIRouter()

    @routes.get("/api/system/settings")
    def settings(request: Request):
        with store.engine.connect() as c:
            require_admin(store, request.state.actor["id"], c)
        config = store.settings
        disk = shutil.disk_usage(config.storage_root)
        return {
            "sources": [
                {
                    "id": hashlib.sha256(str(root.resolve()).encode()).hexdigest(),
                    "name": root.name,
                    "kind": "受控本地目录",
                    "read_only": True,
                }
                for root in config.local_sources
            ],
            "runtime": {
                "max_upload_bytes": config.max_upload_bytes,
                "chunk_bytes": config.upload_chunk_bytes,
                "preview_size": config.preview_size,
                "display_warp_mib": config.display_warp_mib,
                "free_storage_bytes": disk.free,
                "session_hours": 12,
                "secure_cookies": config.secure_cookies,
            },
            "configuration_mode": "deployment_owned",
        }

    @routes.get("/api/management/audit")
    def events(
        request: Request,
        project: str = "",
        search: str = Query("", max_length=200),
        offset: int = Query(0, ge=0),
        limit: int = Query(25, ge=1, le=100),
    ):
        with store.engine.connect() as c:
            actor = request.state.actor["id"]
            if project:
                store.permission(c, actor, project, manage=True)
            else:
                require_admin(store, actor, c)
            condition = [audit.c.project_id == project] if project else []
            if search:
                matching = [
                    key
                    for key, value in ACTION_NAMES.items()
                    if search.casefold() in value.casefold()
                ]
                condition.append(
                    audit.c.action.in_(matching)
                    | audit.c.target.contains(search, autoescape=True)
                    | accounts.c.email.contains(search, autoescape=True)
                )
            joined = audit.outerjoin(accounts, audit.c.actor == accounts.c.id)
            rows = c.execute(
                select(audit, accounts.c.email)
                .select_from(joined)
                .where(*condition)
                .order_by(audit.c.created.desc(), audit.c.id)
                .offset(offset)
                .limit(limit)
            ).mappings()
            items = []
            for row in rows:
                item = dict(row)
                item["action_label"] = ACTION_NAMES.get(row["action"], "管理操作：" + row["action"])
                name = c.scalar(select(projects.c.name).where(projects.c.id == row["target"]))
                if name is None:
                    draft = c.scalar(select(tasks.c.draft).where(tasks.c.id == row["target"]))
                    name = draft.get("title") if draft else None
                if name is None:
                    name = c.scalar(select(accounts.c.email).where(accounts.c.id == row["target"]))
                item["target_name"] = name
                items.append(item)
            return {
                "items": items,
                "total": c.scalar(select(func.count()).select_from(joined).where(*condition)),
                "offset": offset,
                "limit": limit,
            }

    return routes
