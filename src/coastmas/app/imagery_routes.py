"""Authenticated display-only imagery; analysis continues to use original raster assets."""

from typing import Annotated, Self
from urllib.parse import urlsplit

from fastapi import APIRouter, Query, Request, Response
from pydantic import AwareDatetime, Field, FiniteFloat, model_validator

from coastmas.adapters.storage import ArtifactRecord
from coastmas.app.data_routes import data_resource
from coastmas.app.dependencies import CurrentUser, DatabaseSession, artifact_store
from coastmas.core.contracts import Contract, Name
from coastmas.core.errors import CoastMASError
from coastmas.persistence.data_access import require_project_object
from coastmas.persistence.schema import Resource

router = APIRouter(prefix="/api/v1/data-assets", tags=["data"])


class ImageDescription(Contract):
    bounds: tuple[FiniteFloat, FiniteFloat, FiniteFloat, FiniteFloat]
    label: Name
    attribution: Name
    acquired_at: AwareDatetime

    @model_validator(mode="after")
    def geographic(self) -> Self:
        west, south, east, north = self.bounds
        if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
            raise ValueError("image bounds must be ordered WGS84 coordinates")
        return self


class StoredImage(ImageDescription):
    uri: str = Field(max_length=2048)
    checksum: str = Field(pattern=r"^[a-f0-9]{64}$")
    size_bytes: int = Field(strict=True, gt=0, le=4 * 1024 * 1024)


def description(
    identifier: str, version: int, session: DatabaseSession, user_id: str, frame: int = 0
) -> StoredImage | None:
    asset = data_resource(identifier, session, user_id, version)
    field = {0: "visualization", 1: "earlier_visualization"}.get(frame)
    raw = asset.quality.get(field) if field else None
    return StoredImage.model_validate(raw) if raw is not None else None


@router.get("/{identifier}/imagery")
def imagery_metadata(
    identifier: str,
    session: DatabaseSession,
    user_id: CurrentUser,
    version: Annotated[int, Query(ge=1)],
) -> ImageDescription | None:
    stored = description(identifier, version, session, user_id)
    if stored is None:
        return None
    return ImageDescription.model_validate(
        stored.model_dump(exclude={"uri", "checksum", "size_bytes"})
    )


@router.get("/{identifier}/imagery-series")
def imagery_series(
    identifier: str,
    session: DatabaseSession,
    user_id: CurrentUser,
    version: Annotated[int, Query(ge=1)],
) -> list[ImageDescription]:
    result = []
    for frame in (0, 1):
        stored = description(identifier, version, session, user_id, frame)
        if stored is not None:
            result.append(
                ImageDescription.model_validate(
                    stored.model_dump(exclude={"uri", "checksum", "size_bytes"})
                )
            )
    return result


@router.get("/{identifier}/image")
def imagery_content(
    identifier: str,
    request: Request,
    session: DatabaseSession,
    user_id: CurrentUser,
    version: Annotated[int, Query(ge=1)],
    frame: Annotated[int, Query(ge=0)] = 0,
) -> Response:
    stored = description(identifier, version, session, user_id, frame)
    resource = session.get(Resource, identifier)
    if stored is None or resource is None:
        raise CoastMASError("NOT_FOUND", "no imagery for this data version")
    require_project_object(stored.uri, resource.project_id)
    store = artifact_store(request)
    uri = urlsplit(stored.uri)
    if uri.scheme != "s3" or uri.netloc != store.bucket or uri.query or uri.fragment:
        raise CoastMASError("STORAGE_ERROR", "image storage scope is invalid")
    content = store.read(
        ArtifactRecord(store.bucket, uri.path.removeprefix("/"), stored.checksum, stored.size_bytes)
    )
    if not content.startswith(b"\x89PNG\r\n\x1a\n"):
        raise CoastMASError("DATA_FORMAT", "display image must be PNG")
    return Response(
        content,
        media_type="image/png",
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
