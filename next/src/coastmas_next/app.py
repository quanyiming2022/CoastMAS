"""Independent CoastMAS task API. No legacy routes or compatibility dispatch."""

import hashlib
import secrets
from typing import Annotated

from fastapi import FastAPI, File, Form, Request, Response, UploadFile
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import delete, select

from .administration import router as administration_router
from .ahp import router as ahp_router
from .batches import router as batches_router
from .catalog import router as catalog_router
from .collaboration import router as collaboration_router
from .comparison_tasks import router as comparison_router
from .config import Settings
from .contracts import RESEARCH_GOALS, NewTask, SaveDraft, SignIn, TaskDraft
from .execution import router as execution_router
from .geospatial_view import router as geospatial_view_router
from .group_sessions import router as group_sessions_router
from .import_targets import router as import_targets_router
from .indicator_service import router as indicator_service_router
from .input_requirements import router as input_requirements_router
from .input_transactions import router as input_transactions_router
from .intake import Intake, assets
from .knowledge_authoring import router as knowledge_authoring_router
from .logical_intake import router as logical_intake_router
from .management_catalog import router as management_catalog_router
from .method_authoring import router as method_authoring_router
from .method_library import router as method_library_router
from .models import router as models_router
from .outputs import router as outputs_router
from .planning_units import router as planning_units_router
from .planning_versions import router as planning_versions_router
from .process_service import exception as process_exception
from .process_service import router as process_router
from .research_workspace import router as research_workspace_router
from .resource_catalog import router as resource_catalog_router
from .result_views import router as result_views_router
from .reuse import router as reuse_router
from .semantic_authoring import router as semantic_authoring_router
from .source_snapshots import router as source_snapshots_router
from .spatial import router as spatial_router
from .stage_products import router as stage_products_router
from .store import Problem, Store, revisions, sessions, tasks
from .system_settings import router as system_settings_router
from .task_catalog import router as task_catalog_router
from .upload_sessions import router as upload_sessions_router
from .vector_view import router as vector_view_router


def create_app(settings: Settings):
    app = FastAPI(title="CoastMAS Task Workspace", version="2.0.0")
    store = Store(settings)
    app.state.store = store

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        if request.url.path.startswith("/api/ogc/"):
            return process_exception(
                Problem(400, "InvalidParameterValue", "请求不符合已声明的标准服务子集"), request
            )
        return await request_validation_exception_handler(request, exc)

    @app.exception_handler(Problem)
    async def problem_handler(request: Request, problem: Problem):
        if request.url.path.startswith("/api/ogc/"):
            return process_exception(problem, request)
        return JSONResponse(
            status_code=problem.status,
            content={"code": problem.code, "message": problem.message, "details": problem.details},
        )

    @app.middleware("http")
    async def session_boundary(request: Request, call_next):
        if request.url.path.startswith("/api/") and request.url.path != "/api/session":
            try:
                actor = store.authenticate(request.cookies.get("coastmas_next_session"))
                if request.method not in {"GET", "HEAD", "OPTIONS"} and not secrets.compare_digest(
                    request.headers.get("X-CSRF-Token", ""), actor["csrf"]
                ):
                    raise Problem(403, "CSRF_REQUIRED", "请求缺少有效的会话验证")
                request.state.actor = actor
            except Problem as exc:
                if request.url.path.startswith("/api/ogc/"):
                    return process_exception(exc, request)
                return JSONResponse(
                    status_code=exc.status, content={"code": exc.code, "message": exc.message}
                )
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/health")
    def health():
        with store.engine.connect() as c:
            c.execute(select(1))
        return {"status": "ready", "edition": "next"}

    @app.post("/api/session")
    def login(body: SignIn, response: Response):
        token, csrf = store.sign_in(body.email, body.password)
        response.set_cookie(
            "coastmas_next_session",
            token,
            httponly=True,
            secure=settings.secure_cookies,
            samesite="strict",
            max_age=43200,
        )
        return {"csrf": csrf, "user": store.authenticate(token)}

    @app.get("/api/session")
    def current_session(request: Request):
        return store.authenticate(request.cookies.get("coastmas_next_session"))

    @app.delete("/api/session")
    def logout(request: Request, response: Response):
        actor = store.authenticate(request.cookies.get("coastmas_next_session"))
        if not secrets.compare_digest(request.headers.get("X-CSRF-Token", ""), actor["csrf"]):
            raise Problem(403, "CSRF_REQUIRED", "请求缺少有效的会话验证")
        with store.engine.begin() as c:
            c.execute(
                delete(sessions).where(
                    sessions.c.digest
                    == hashlib.sha256(request.cookies["coastmas_next_session"].encode()).hexdigest()
                )
            )
        response.delete_cookie("coastmas_next_session")
        return {"signed_out": True}

    @app.get("/api/projects")
    def project_list(request: Request):
        return store.project_list(request.state.actor["id"])

    @app.get("/api/research-goals")
    def research_goals():
        return [
            {"id": key, "label": value["label"], "capability": value["capability"]}
            for key, value in RESEARCH_GOALS.items()
        ]

    @app.post("/api/tasks", status_code=201)
    def create_task(body: NewTask, request: Request):
        return store.new_task(
            request.state.actor["id"],
            body.project_id,
            TaskDraft(
                title=body.title,
                purpose=body.purpose,
                options=(
                    {"task_type": body.task_type}
                    if body.task_type
                    else {"business_goal": body.goal}
                    if body.goal
                    else {"operator": "valid_mask", "band": 1}
                    if body.purpose == "spatial"
                    else {}
                ),
            ).model_dump(mode="json"),
        )

    @app.get("/api/projects/{project}/tasks")
    def task_list(project: str, request: Request):
        with store.engine.connect() as c:
            store.permission(c, request.state.actor["id"], project)
            return [
                dict(r)
                for r in c.execute(
                    select(tasks)
                    .where(tasks.c.project_id == project)
                    .order_by(tasks.c.updated.desc())
                ).mappings()
            ]

    @app.get("/api/tasks/{task}")
    def read_task(task: str, request: Request):
        return store.task(request.state.actor["id"], task)

    @app.put("/api/tasks/{task}")
    def save_task(task: str, body: SaveDraft, request: Request):
        return store.save_task(
            request.state.actor["id"],
            task,
            body.expected_revision,
            body.draft.model_dump(mode="json"),
        )

    @app.get("/api/tasks/{task}/history")
    def history(task: str, request: Request):
        store.task(request.state.actor["id"], task)
        with store.engine.connect() as c:
            return [
                dict(r)
                for r in c.execute(
                    select(revisions)
                    .where(revisions.c.task_id == task)
                    .order_by(revisions.c.revision)
                ).mappings()
            ]

    intake = Intake(store)

    @app.post("/api/projects/{project}/assets", status_code=201)
    def upload(
        project: str,
        request: Request,
        file: Annotated[UploadFile, File()],
        task_id: Annotated[str | None, Form()] = None,
        expected_revision: Annotated[int | None, Form()] = None,
    ):
        return intake.ingest(
            request.state.actor["id"],
            project,
            file.file,
            file.filename or "data",
            task_id,
            expected_revision,
        )

    @app.get("/api/projects/{project}/assets")
    def asset_list(project: str, request: Request):
        with store.engine.connect() as c:
            store.permission(c, request.state.actor["id"], project)
            return [
                dict(row)
                for row in c.execute(
                    select(assets)
                    .where(assets.c.project_id == project)
                    .order_by(assets.c.created.desc())
                ).mappings()
            ]

    @app.get("/api/assets/{asset_id}")
    def asset_detail(asset_id: str, request: Request):
        return intake.read_asset(request.state.actor["id"], asset_id)

    @app.get("/api/assets/{asset_id}/download")
    def download(asset_id: str, request: Request):
        asset = intake.read_asset(request.state.actor["id"], asset_id)
        if asset["facts"].get("logical_package"):
            from .package_download import package_download

            return package_download(settings, asset)
        return FileResponse(
            settings.storage_root / asset["object_key"],
            filename=asset["name"],
            media_type="application/octet-stream",
        )

    app.include_router(group_sessions_router(store))
    app.include_router(logical_intake_router(store))
    app.include_router(input_transactions_router(store))
    app.include_router(upload_sessions_router(store))
    app.include_router(catalog_router(store))
    app.include_router(task_catalog_router(store))
    app.include_router(management_catalog_router(store))
    app.include_router(research_workspace_router(store))
    app.include_router(stage_products_router(store))
    app.include_router(input_requirements_router(store))
    app.include_router(indicator_service_router(store))
    app.include_router(planning_versions_router(store))
    app.include_router(planning_units_router(store))
    app.include_router(import_targets_router(store))
    app.include_router(resource_catalog_router(store))
    app.include_router(geospatial_view_router(store))
    app.include_router(vector_view_router(store))
    app.include_router(outputs_router(store))
    app.include_router(result_views_router(store))
    app.include_router(spatial_router(store))
    app.include_router(source_snapshots_router(store))
    app.include_router(models_router(store))
    app.include_router(reuse_router(store))
    app.include_router(batches_router(store))
    app.include_router(administration_router(store))
    app.include_router(ahp_router(store))
    app.include_router(system_settings_router(store))
    app.include_router(method_authoring_router(store))
    app.include_router(method_library_router(store))
    app.include_router(knowledge_authoring_router(store))
    app.include_router(semantic_authoring_router(store))
    app.include_router(execution_router(store))
    app.include_router(process_router(store))
    app.include_router(comparison_router(store))
    app.include_router(collaboration_router(store))
    if settings.web_root is not None:
        web_root = settings.web_root.resolve(strict=True)
        app.mount("/assets", StaticFiles(directory=web_root / "assets"), name="web-assets")

        @app.get("/{route:path}")
        def workspace_page(route: str):
            if route.startswith("api/") or route == "api":
                raise Problem(404, "NOT_FOUND", "接口不存在")
            return FileResponse(web_root / "index.html", media_type="text/html")

    return app
