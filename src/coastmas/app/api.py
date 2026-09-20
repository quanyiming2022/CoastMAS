"""FastAPI with server-side project authorization and explicit transaction commits."""

import logging
import os
import traceback
from dataclasses import asdict
from typing import cast
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, JsonValue, SecretStr, ValidationError
from sqlalchemy import Engine, create_engine, select, text
from starlette.exceptions import HTTPException

from coastmas.adapters.storage import S3ArtifactStore
from coastmas.app.data_routes import router as data_router
from coastmas.app.dependencies import CurrentUser, DatabaseSession
from coastmas.app.model_routes import router as model_router
from coastmas.app.planning_routes import router as planning_router
from coastmas.app.run_routes import router as run_router
from coastmas.core.contracts import Contract, DataAssetSpec, ModelSpec, SceneSpec, WorkflowSpec
from coastmas.core.errors import CoastMASError
from coastmas.core.execution import ExecutionRegistry
from coastmas.core.llm import LLMProvider
from coastmas.core.model_documents import reject_embedded_credentials
from coastmas.persistence.auth import login, logout
from coastmas.persistence.database import local_database_url
from coastmas.persistence.resources import (
    create_resource,
    read_resource,
    require_permission,
    update_resource,
)
from coastmas.persistence.schema import Resource

LOG = logging.getLogger("coastmas.api")


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=320)
    password: SecretStr = Field(min_length=1, max_length=256)


class CreateRequest(Contract):
    project_id: str
    spec: dict[str, JsonValue]


class UpdateRequest(Contract):
    expected_version: int = Field(ge=1)
    spec: dict[str, JsonValue]


def error_response(
    request: Request, code: str, message: str, status: int, details: JsonValue = None
) -> JSONResponse:
    request_id = str(uuid4())
    return JSONResponse(
        status_code=status,
        content={
            "error_code": code,
            "message": message,
            "details": details,
            "request_id": request_id,
        },
        headers={"X-Request-ID": request_id},
    )


def register_resource_routes(app: FastAPI, path: str, kind: str, contract: type[Contract]) -> None:
    def list_items(
        project_id: str, session: DatabaseSession, user_id: CurrentUser
    ) -> list[dict[str, JsonValue]]:
        require_permission(session, user_id, project_id, "read")
        records = session.scalars(
            select(Resource)
            .where(
                Resource.project_id == project_id,
                Resource.kind == kind,
                Resource.archived.is_(False),
            )
            .order_by(Resource.name)
            .limit(500)
        )
        return [
            {
                "id": item.id,
                "name": item.name,
                "version": item.current_version,
                "enabled": item.enabled,
                "published": item.published,
            }
            for item in records
        ]

    def create_item(
        body: CreateRequest, session: DatabaseSession, user_id: CurrentUser
    ) -> dict[str, JsonValue]:
        validated = contract.model_validate(body.spec)
        if isinstance(validated, ModelSpec):
            reject_embedded_credentials(validated.runtime_config)
            if (
                validated.validation_status != "UNVALIDATED"
                or validated.execution_status != "NOT_EXECUTABLE"
            ):
                raise CoastMASError(
                    "MODEL_REGISTRATION_REQUIRED",
                    "model execution and validation require trusted registration",
                )
        if isinstance(validated, DataAssetSpec):
            validated = validated.model_copy(
                update={"quality": {**validated.quality, "validated": False}}
            )
        spec = validated.model_dump(mode="json")
        identifier, name = spec.get("id"), spec.get("name")
        if not isinstance(identifier, str) or not isinstance(name, str):
            raise CoastMASError("VALIDATION_ERROR", "resource identity and name required")
        result = create_resource(
            session,
            user_id=user_id,
            project_id=body.project_id,
            kind=kind,
            identifier=identifier,
            name=name,
            spec=spec,
        )
        session.commit()
        return cast(dict[str, JsonValue], asdict(result))

    def get_item(
        identifier: str, session: DatabaseSession, user_id: CurrentUser, version: int | None = None
    ) -> dict[str, JsonValue]:
        resource = session.get(Resource, identifier)
        if resource is None or resource.kind != kind:
            raise CoastMASError("NOT_FOUND", "resource unavailable")
        return cast(
            dict[str, JsonValue],
            asdict(read_resource(session, user_id=user_id, identifier=identifier, version=version)),
        )

    def update_item(
        identifier: str, body: UpdateRequest, session: DatabaseSession, user_id: CurrentUser
    ) -> dict[str, JsonValue]:
        resource = session.get(Resource, identifier)
        if resource is None or resource.kind != kind:
            raise CoastMASError("NOT_FOUND", "resource unavailable")
        validated = contract.model_validate(body.spec)
        if isinstance(validated, ModelSpec):
            reject_embedded_credentials(validated.runtime_config)
            if (
                validated.validation_status != "UNVALIDATED"
                or validated.execution_status != "NOT_EXECUTABLE"
            ):
                raise CoastMASError(
                    "MODEL_REGISTRATION_REQUIRED", "edited model requires trusted revalidation"
                )

        if isinstance(validated, DataAssetSpec):
            validated = validated.model_copy(
                update={"quality": {**validated.quality, "validated": False}}
            )
        result = update_resource(
            session,
            user_id=user_id,
            identifier=identifier,
            expected_version=body.expected_version,
            spec=validated.model_dump(mode="json"),
        )
        session.commit()
        return cast(dict[str, JsonValue], asdict(result))

    app.add_api_route(path, list_items, methods=["GET"], name=f"list_{kind}")
    app.add_api_route(path, create_item, methods=["POST"], status_code=201, name=f"create_{kind}")
    app.add_api_route(path + "/{identifier}", get_item, methods=["GET"], name=f"get_{kind}")
    app.add_api_route(path + "/{identifier}", update_item, methods=["PUT"], name=f"update_{kind}")


def create_app(
    engine: Engine | None = None,
    registry: ExecutionRegistry | None = None,
    artifact_store: S3ArtifactStore | None = None,
    llm_provider: LLMProvider | None = None,
) -> FastAPI:
    app = FastAPI(title=os.environ.get("COASTMAS_BRAND_NAME", "CoastMAS"), version="0.1.0")
    app.state.engine = (
        engine if engine is not None else create_engine(local_database_url(), pool_pre_ping=True)
    )

    @app.exception_handler(CoastMASError)
    async def domain_error(request: Request, exc: CoastMASError) -> JSONResponse:
        statuses = {
            "AUTHENTICATION_ERROR": 401,
            "AUTHORIZATION_ERROR": 403,
            "CSRF_ERROR": 403,
            "NOT_FOUND": 404,
            "VERSION_CONFLICT": 409,
            "IDEMPOTENCY_CONFLICT": 409,
            "DEPENDENCY_CONFLICT": 409,
        }
        return error_response(
            request, exc.code, exc.message, statuses.get(exc.code, 422), exc.details
        )

    @app.exception_handler(RequestValidationError)
    @app.exception_handler(ValidationError)
    async def validation_error(
        request: Request, exc: RequestValidationError | ValidationError
    ) -> JSONResponse:
        # Do not echo rejected input values: they may contain passwords or sensitive data.
        details: list[JsonValue] = [
            {"location": list(item["loc"]), "type": item["type"]} for item in exc.errors()
        ]
        return error_response(
            request, "VALIDATION_ERROR", "request does not match contract", 422, details
        )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return error_response(request, "HTTP_ERROR", "request unavailable", exc.status_code)

    @app.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception) -> JSONResponse:
        frames = traceback.StackSummary.extract(traceback.walk_tb(exc.__traceback__))
        LOG.error("Unhandled %s at %s", type(exc).__name__, "".join(frames.format()))
        return error_response(
            request, "INTERNAL_ERROR", "operation failed; consult server log", 500
        )

    @app.get("/health")
    def health(session: DatabaseSession) -> dict[str, str]:
        session.execute(text("SELECT 1"))
        return {"status": "healthy"}

    @app.post("/api/v1/auth/login")
    def sign_in(body: LoginRequest, response: Response, session: DatabaseSession) -> dict[str, str]:
        tokens = login(session, body.email, body.password.get_secret_value())
        session.commit()
        secure = os.environ.get("COASTMAS_SECURE_COOKIES", "false").lower() == "true"
        response.set_cookie(
            "coastmas_session",
            tokens.session_token,
            httponly=True,
            secure=secure,
            samesite="strict",
            max_age=28800,
        )
        response.set_cookie(
            "coastmas_csrf",
            tokens.csrf_token,
            httponly=False,
            secure=secure,
            samesite="strict",
            max_age=28800,
        )
        return {"user_id": tokens.user_id, "csrf_token": tokens.csrf_token}

    @app.post("/api/v1/auth/logout", status_code=204)
    def sign_out(
        request: Request, response: Response, session: DatabaseSession, user_id: CurrentUser
    ) -> None:
        logout(session, request.cookies["coastmas_session"])
        session.commit()
        response.delete_cookie("coastmas_session")
        response.delete_cookie("coastmas_csrf")

    @app.get("/api/v1/auth/me")
    def current_user(user_id: CurrentUser) -> dict[str, str]:
        return {"user_id": user_id}

    app.state.artifact_store = artifact_store
    app.state.registry = registry if registry is not None else ExecutionRegistry()
    app.include_router(data_router)
    app.include_router(model_router)
    app.include_router(run_router)
    app.include_router(planning_router)
    app.state.llm_provider = llm_provider
    routes: list[tuple[str, str, type[Contract]]] = [
        ("models", "model", ModelSpec),
        ("data-assets", "data", DataAssetSpec),
        ("scenes", "scene", SceneSpec),
        ("workflows", "workflow", WorkflowSpec),
    ]
    for path, kind, contract in routes:
        register_resource_routes(app, "/api/v1/" + path, kind, contract)
    return app
