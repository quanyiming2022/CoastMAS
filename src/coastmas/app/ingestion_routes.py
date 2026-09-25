"""Import real raster bytes from upload or an explicitly project-authorized local root."""

import json
import os
import stat
import tempfile
from dataclasses import asdict
from pathlib import Path, PurePosixPath
from typing import Annotated, BinaryIO, cast
from uuid import uuid4

from fastapi import APIRouter, File, Form, Query, Request, UploadFile
from pydantic import Field, JsonValue

from coastmas.adapters.runtime import PythonFunctionAdapter, RunRequest
from coastmas.app.dependencies import CurrentUser, DatabaseSession, artifact_store
from coastmas.configuration import configuration_value
from coastmas.core.contracts import Contract, DataAssetSpec, Name
from coastmas.core.data_inspection import DataInspection
from coastmas.core.errors import CoastMASError
from coastmas.core.file_ingestion import (
    MAX_FILE_BYTES,
    IntakeDeclaration,
    inspect_raster_file,
    snapshot_file,
)
from coastmas.persistence.resources import create_resource, require_permission

router = APIRouter(prefix="/api/v1/data-assets", tags=["data"])


def _inspect(
    inputs: dict[str, JsonValue], parameters: dict[str, JsonValue]
) -> dict[str, JsonValue]:
    path = inputs.get("path")
    if not isinstance(path, str):
        raise CoastMASError("DATA_FORMAT", "private snapshot missing")
    asset = DataAssetSpec.model_validate(inputs["asset"]) if inputs.get("asset") else None
    return inspect_raster_file(Path(path), asset).model_dump(mode="json")


def inspect_disk(path: Path, asset: DataAssetSpec | None = None) -> DataInspection:
    adapter = PythonFunctionAdapter({"inspect": _inspect}, max_output_bytes=4194304)
    result = adapter.run(
        RunRequest(
            handler="inspect",
            inputs={"path": str(path), "asset": asset.model_dump(mode="json") if asset else None},
            parameters={},
            work_root=path.parent,
            timeout_seconds=180,
        )
    )
    return DataInspection.model_validate(result.outputs)


def ingest_stream(
    stream: BinaryIO,
    declaration: IntakeDeclaration,
    project_id: str,
    request: Request,
    session: DatabaseSession,
    user_id: str,
) -> dict[str, JsonValue]:
    with tempfile.TemporaryDirectory(prefix="coastmas-ingest-") as temporary:
        path = Path(temporary) / "source.tif"
        checksum = snapshot_file(stream, path)
        report = inspect_disk(path)
        facts = cast(dict[str, JsonValue], report.metadata["file_facts"])
        if checksum != facts["sha256"]:
            raise CoastMASError("CHECKSUM_ERROR", "snapshot changed during import")
        artifact = artifact_store(request).put_file(
            f"{project_id}/data/{uuid4().hex}/{checksum}", path, max_bytes=MAX_FILE_BYTES
        )
        asset = DataAssetSpec(
            id="data:" + uuid4().hex,
            name=declaration.name,
            type="raster",
            format="GeoTIFF",
            uri=artifact.uri,
            checksum=checksum,
            crs=cast(str | None, facts["crs"]),
            vertical_datum=None,
            spatial_extent=None,
            time_start=None,
            time_end=None,
            time_resolution=None,
            variables=(),
            source=declaration.source,
            license=declaration.license,
            version=1,
            quality={**report.metadata, "declarations": declaration.model_dump(mode="json")},
        )
        revision = create_resource(
            session,
            user_id=user_id,
            project_id=project_id,
            kind="data",
            identifier=asset.id,
            name=asset.name,
            spec=asset.model_dump(mode="json"),
        )
        session.commit()
        return cast(dict[str, JsonValue], asdict(revision))


@router.post("/ingest", status_code=201)
def ingest(
    request: Request,
    session: DatabaseSession,
    user_id: CurrentUser,
    project_id: Annotated[str, Form(max_length=128)],
    declaration: Annotated[str, Form(max_length=4096)],
    file: Annotated[UploadFile, File()],
) -> dict[str, JsonValue]:
    require_permission(session, user_id, project_id, "write")
    return ingest_stream(
        file.file,
        IntakeDeclaration.model_validate_json(declaration),
        project_id,
        request,
        session,
        user_id,
    )


def roots(project_id: str) -> dict[str, Path]:
    try:
        raw = json.loads(configuration_value("COASTMAS_LOCAL_IMPORT_ROOTS", "{}"))
        if not isinstance(raw, dict):
            raise ValueError("root config must be an object")
        result = {}
        for alias, setting in raw.items():
            if (
                not isinstance(setting, dict)
                or not isinstance(setting.get("project_ids"), list)
                or not isinstance(setting.get("path"), str)
            ):
                raise ValueError("invalid local root config")
            if project_id in setting["project_ids"]:
                result[alias] = Path(setting["path"]).resolve(strict=True)
        return result
    except (ValueError, OSError) as exc:
        raise CoastMASError("CONFIGURATION_ERROR", "local import roots unavailable") from exc


@router.get("/local-files")
def local_files(
    project_id: str,
    session: DatabaseSession,
    user_id: CurrentUser,
    source: str | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, JsonValue]:
    require_permission(session, user_id, project_id, "write")
    available = roots(project_id)
    if source is None:
        return {"sources": list(available), "files": [], "total": 0}
    if source not in available:
        raise CoastMASError("AUTHORIZATION_ERROR", "local source not authorized for project")
    root = available[source]
    files: list[dict[str, JsonValue]] = []
    for directory, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(
            name
            for name in dirs
            if not name.startswith(".") and not (Path(directory) / name).is_symlink()
        )
        for name in sorted(names):
            path = Path(directory) / name
            if (
                path.suffix.lower() not in {".tif", ".tiff"}
                or path.is_symlink()
                or not path.is_file()
            ):
                continue
            files.append(
                {"path": path.relative_to(root).as_posix(), "size_bytes": path.stat().st_size}
            )
            if len(files) > 10000:
                raise CoastMASError("DATA_LIMIT", "local source exceeds listing budget")
    return {
        "sources": list(available),
        "files": cast(list[JsonValue], files[offset : offset + limit]),
        "total": len(files),
    }


class LocalImport(Contract):
    project_id: Name
    source: Name
    path: str = Field(min_length=1, max_length=2048)
    declaration: IntakeDeclaration


@router.post("/ingest-local", status_code=201)
def ingest_local(
    body: LocalImport, request: Request, session: DatabaseSession, user_id: CurrentUser
) -> dict[str, JsonValue]:
    require_permission(session, user_id, body.project_id, "write")
    root = roots(body.project_id).get(body.source)
    relative = PurePosixPath(body.path)
    if (
        root is None
        or relative.is_absolute()
        or any(part in ("..", ".") for part in body.path.split("/"))
        or "\\" in body.path
    ):
        raise CoastMASError("AUTHORIZATION_ERROR", "local path is not authorized")
    # Walk file descriptors with no-follow, so symlink replacement cannot escape the root.
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in relative.parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        handle = os.open(
            relative.parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor
        )
        with os.fdopen(handle, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise CoastMASError("AUTHORIZATION_ERROR", "only regular local files are allowed")
            return ingest_stream(
                stream, body.declaration, body.project_id, request, session, user_id
            )
    except OSError as exc:
        raise CoastMASError("AUTHORIZATION_ERROR", "local file unavailable or unsafe") from exc
    finally:
        os.close(descriptor)
