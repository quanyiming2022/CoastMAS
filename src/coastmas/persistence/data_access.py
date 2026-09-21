"""Bind stored-object reads to their owning project, not user-supplied catalog metadata."""

from urllib.parse import urlsplit

from coastmas.core.errors import CoastMASError


def require_project_object(uri: str, project_id: str) -> None:
    address = urlsplit(uri)
    key = address.path.removeprefix("/")
    if address.scheme == "s3" and not key.startswith(
        (project_id + "/", "samples/" + project_id + "/")
    ):
        raise CoastMASError("AUTHORIZATION_ERROR", "stored object is outside this project")
