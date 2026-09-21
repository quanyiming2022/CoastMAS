"""File uploads and verified previews using project-scoped immutable storage."""

import base64
import hashlib
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, cast
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import APIRouter, File, Form, Query, Request, Response, UploadFile
from pydantic import Field, JsonValue

from coastmas.adapters.runtime import PythonFunctionAdapter, RunRequest
from coastmas.adapters.storage import ArtifactRecord
from coastmas.app.dependencies import CurrentUser, DatabaseSession, artifact_store
from coastmas.core.contracts import Contract, DataAssetSpec
from coastmas.core.data_inspection import MAX_BYTES, DataInspection, inspect_data
from coastmas.core.errors import CoastMASError
from coastmas.persistence.data_access import require_project_object
from coastmas.persistence.lifecycle import archive_resource, resource_history
from coastmas.persistence.resources import (
    create_resource,
    read_resource,
    require_permission,
    update_resource,
)
from coastmas.persistence.schema import Resource

router = APIRouter(prefix="/api/v1/data-assets", tags=["data"])


def _inspection_handler(
    inputs: dict[str, JsonValue], parameters: dict[str, JsonValue]
) -> dict[str, JsonValue]:
    encoded = inputs.get("content")
    if not isinstance(encoded, str):
        raise CoastMASError("DATA_FORMAT", "inspection input is missing")
    data = DataAssetSpec.model_validate(inputs.get("asset"))
    report = inspect_data(base64.b64decode(encoded, validate=True), data)
    return report.model_dump(mode="json")


def inspect_isolated(content: bytes, data: DataAssetSpec) -> DataInspection:
    # Native GDAL/netCDF parsing receives its own process, timeout and clean environment.
    # netCDF's C library cannot safely handle parallel I/O in application threads.
    adapter = PythonFunctionAdapter({"inspect": _inspection_handler}, max_output_bytes=4_194_304)
    with tempfile.TemporaryDirectory(prefix="coastmas-inspection-") as temporary:
        result = adapter.run(
            RunRequest(
                handler="inspect",
                inputs={
                    "content": base64.b64encode(content).decode("ascii"),
                    "asset": data.model_dump(mode="json"),
                },
                parameters={},
                work_root=Path(temporary),
                timeout_seconds=30,
            )
        )
    return DataInspection.model_validate(result.outputs)


class ValidateDataRequest(Contract):
    expected_version: int = Field(ge=1)


def data_resource(
    identifier: str,
    session: DatabaseSession,
    user_id: str,
    version: int | None = None,
) -> DataAssetSpec:
    resource = session.get(Resource, identifier)
    if resource is None or resource.kind != "data":
        raise CoastMASError("NOT_FOUND", "data asset unavailable")
    return DataAssetSpec.model_validate(
        read_resource(
            session,
            user_id=user_id,
            identifier=identifier,
            version=version,
        ).spec
    )


def stored_content(request: Request, session: DatabaseSession, data: DataAssetSpec) -> bytes:
    resource = session.get(Resource, data.id)
    if resource is None:
        raise CoastMASError("NOT_FOUND", "data resource unavailable")
    require_project_object(data.uri, resource.project_id)
    store = artifact_store(request)
    uri = urlsplit(data.uri)
    size = data.quality.get("size_bytes")
    if (
        uri.scheme != "s3"
        or uri.netloc != store.bucket
        or uri.query
        or uri.fragment
        or not isinstance(size, int)
        or isinstance(size, bool)
    ):
        raise CoastMASError(
            "STORAGE_ERROR", "data inspection requires a configured stored artifact"
        )
    content = store.read(
        ArtifactRecord(store.bucket, uri.path.removeprefix("/"), data.checksum, size)
    )
    return content


def inspect_stored(
    request: Request, session: DatabaseSession, data: DataAssetSpec
) -> DataInspection:
    return inspect_isolated(stored_content(request, session, data), data)


@router.post("/upload", status_code=201)
def upload(
    request: Request,
    session: DatabaseSession,
    user_id: CurrentUser,
    project_id: Annotated[str, Form(max_length=128)],
    metadata: Annotated[str, Form(max_length=262144)],
    file: Annotated[UploadFile, File()],
) -> dict[str, JsonValue]:
    require_permission(session, user_id, project_id, "write")
    source = DataAssetSpec.model_validate_json(metadata)
    if source.version != 1:
        raise CoastMASError("VERSION_CONFLICT", "new upload requires initial version 1")
    if session.get(Resource, source.id) is not None:
        raise CoastMASError("VERSION_CONFLICT", "data identity already exists")
    content = file.file.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise CoastMASError("DATA_LIMIT", "upload exceeds configured file budget")
    digest = hashlib.sha256(content).hexdigest()
    measured = source.model_copy(update={"checksum": digest})
    report = inspect_isolated(content, measured)
    store = artifact_store(request)
    artifact = store.put(f"{project_id}/data/{uuid4().hex}/{digest}", content)
    measured = measured.model_copy(
        update={
            "uri": artifact.uri,
            "quality": {**source.quality, **report.metadata},
        }
    )
    result = create_resource(
        session,
        user_id=user_id,
        project_id=project_id,
        kind="data",
        identifier=measured.id,
        name=measured.name,
        spec=measured.model_dump(mode="json"),
    )
    session.commit()
    return cast(dict[str, JsonValue], asdict(result))


@router.get("/{identifier}/preview")
def preview(
    identifier: str,
    request: Request,
    response: Response,
    session: DatabaseSession,
    user_id: CurrentUser,
    version: int | None = Query(default=None, ge=1),
) -> DataInspection:
    data = data_resource(identifier, session, user_id, version)
    response.headers["Cache-Control"] = "no-store"
    return inspect_stored(request, session, data)


@router.post("/{identifier}/validate")
def validate(
    identifier: str,
    body: ValidateDataRequest,
    request: Request,
    session: DatabaseSession,
    user_id: CurrentUser,
) -> dict[str, JsonValue]:
    data = data_resource(identifier, session, user_id, body.expected_version)
    resource = session.get(Resource, identifier)
    if resource is None:
        raise CoastMASError("NOT_FOUND", "data asset unavailable")
    require_permission(session, user_id, resource.project_id, "write")
    report = inspect_stored(request, session, data)
    updated = data.model_copy(
        update={
            "version": body.expected_version + 1,
            "quality": {**data.quality, **report.metadata},
        }
    )
    revision = update_resource(
        session,
        user_id=user_id,
        identifier=identifier,
        expected_version=body.expected_version,
        spec=updated.model_dump(mode="json"),
    )
    session.commit()
    return cast(dict[str, JsonValue], asdict(revision))


@router.get("/{identifier}/versions")
def history(
    identifier: str, session: DatabaseSession, user_id: CurrentUser
) -> list[dict[str, JsonValue]]:
    data_resource(identifier, session, user_id)
    return [
        cast(dict[str, JsonValue], asdict(revision))
        for revision in resource_history(session, user_id=user_id, identifier=identifier)
    ]


@router.get("/{identifier}/download")
def download(
    identifier: str,
    request: Request,
    session: DatabaseSession,
    user_id: CurrentUser,
    version: int | None = Query(default=None, ge=1),
) -> Response:
    data = data_resource(identifier, session, user_id, version)
    return Response(
        stored_content(request, session, data),
        media_type="application/octet-stream",
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": 'attachment; filename="coastmas-data-v'
            + str(data.version)
            + '.bin"',
            "ETag": '"' + data.checksum + '"',
        },
    )


@router.delete("/{identifier}", status_code=204)
def archive(identifier: str, session: DatabaseSession, user_id: CurrentUser) -> None:
    data_resource(identifier, session, user_id)
    archive_resource(session, user_id=user_id, identifier=identifier)
    session.commit()
