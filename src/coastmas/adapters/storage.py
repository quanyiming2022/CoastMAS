"""S3/MinIO immutable object storage with checksums and bounded transfers."""

import hashlib
import re
from dataclasses import dataclass, field
from typing import Protocol, cast

# These are the only untyped SDK import boundaries; responses use explicit structural checks.
import boto3  # type: ignore[import-untyped]
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from coastmas.configuration import configuration_value
from coastmas.core.errors import CoastMASError


@dataclass(frozen=True)
class StorageSettings:
    endpoint: str
    access_key: str = field(repr=False)
    secret_key: str = field(repr=False)


@dataclass(frozen=True)
class ArtifactRecord:
    bucket: str
    key: str
    sha256: str
    size: int

    @property
    def uri(self) -> str:
        return f"s3://{self.bucket}/{self.key}"


class ReadableBody(Protocol):
    def read(self, amt: int) -> bytes: ...
    def close(self) -> None: ...


class S3Client(Protocol):
    def head_bucket(self, *, Bucket: str) -> dict[str, object]: ...
    def create_bucket(self, *, Bucket: str) -> dict[str, object]: ...
    def put_object(
        self, *, Bucket: str, Key: str, Body: bytes, IfNoneMatch: str, Metadata: dict[str, str]
    ) -> dict[str, object]: ...
    def get_object(self, *, Bucket: str, Key: str) -> dict[str, object]: ...


def local_storage_settings() -> StorageSettings:
    return StorageSettings(
        configuration_value("S3_ENDPOINT", "http://127.0.0.1:59000"),
        configuration_value("MINIO_ROOT_USER"),
        configuration_value("MINIO_ROOT_PASSWORD"),
    )


class S3ArtifactStore:
    def __init__(
        self, settings: StorageSettings, *, bucket: str, max_bytes: int = 64 * 1024 * 1024
    ):
        if re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", bucket) is None or max_bytes <= 0:
            raise CoastMASError("VALIDATION_ERROR", "invalid bucket or storage budget")
        self.bucket = bucket
        self.max_bytes = max_bytes
        self.client = cast(
            S3Client,
            boto3.client(
                "s3",
                endpoint_url=settings.endpoint,
                aws_access_key_id=settings.access_key,
                aws_secret_access_key=settings.secret_key,
                region_name="us-east-1",
            ),
        )

    @staticmethod
    def validate_key(key: str) -> None:
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9/_.-]{0,1023}", key) is None or any(
            part in ("", ".", "..") for part in key.split("/")
        ):
            raise CoastMASError("VALIDATION_ERROR", "unsafe object key")

    def ensure_bucket(self) -> None:
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError as exc:
            if str(exc.response.get("Error", {}).get("Code")) not in {"404", "NoSuchBucket"}:
                raise CoastMASError(
                    "STORAGE_ERROR", "object storage bucket is unavailable"
                ) from exc
            self.client.create_bucket(Bucket=self.bucket)

    def put(self, key: str, content: bytes) -> ArtifactRecord:
        self.validate_key(key)
        if len(content) > self.max_bytes:
            raise CoastMASError("STORAGE_LIMIT", "artifact exceeds configured byte budget")
        digest = hashlib.sha256(content).hexdigest()
        artifact = ArtifactRecord(self.bucket, key, digest, len(content))
        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=content,
                IfNoneMatch="*",
                Metadata={"sha256": digest},
            )
        except ClientError as exc:
            if str(exc.response.get("Error", {}).get("Code")) not in {"PreconditionFailed", "412"}:
                raise CoastMASError("STORAGE_ERROR", "artifact upload failed") from exc
            try:
                existing = self.read(artifact)
            except CoastMASError as mismatch:
                raise CoastMASError(
                    "IMMUTABLE_CONFLICT", "immutable artifact key already exists"
                ) from mismatch
            if existing != content:
                raise CoastMASError(
                    "IMMUTABLE_CONFLICT", "immutable artifact key already exists"
                ) from exc
        # Read-back validates content, not just metadata supplied by a client.
        self.read(artifact)
        return artifact

    def read(self, artifact: ArtifactRecord) -> bytes:
        self.validate_key(artifact.key)
        if artifact.bucket != self.bucket or not 0 <= artifact.size <= self.max_bytes:
            raise CoastMASError("STORAGE_ERROR", "artifact scope or size invalid")
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=artifact.key)
        except ClientError as exc:
            raise CoastMASError("STORAGE_ERROR", "artifact cannot be read") from exc
        raw_body = response.get("Body")
        if raw_body is None or not hasattr(raw_body, "read") or not hasattr(raw_body, "close"):
            raise CoastMASError("STORAGE_ERROR", "object storage returned invalid body")
        body = cast(ReadableBody, raw_body)
        try:
            content = body.read(self.max_bytes + 1)
        finally:
            body.close()
        if len(content) != artifact.size or hashlib.sha256(content).hexdigest() != artifact.sha256:
            raise CoastMASError("CHECKSUM_ERROR", "artifact size or checksum mismatch")
        return content
