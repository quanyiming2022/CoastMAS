"""Verify all persisted S3 references and exercise only a newly owned test bucket."""

import argparse
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from urllib.parse import urlsplit
from urllib.request import urlopen
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from coastmas.adapters.storage import ArtifactRecord, S3ArtifactStore, local_storage_settings
from coastmas.core.contracts import DataAssetSpec
from coastmas.persistence.database import local_database_url
from coastmas.persistence.resources import fingerprint
from coastmas.persistence.schema import Resource, ResourceVersion, ResultBundle


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", default="http://127.0.0.1:59100")
    parser.add_argument("--seconds", type=int, default=120)
    args = parser.parse_args()
    if args.endpoint not in {"http://127.0.0.1:59100", "http://127.0.0.1:59000"}:
        raise SystemExit("Verification endpoint must be one of the project-local services")
    if not 60 <= args.seconds <= 600:
        raise SystemExit("Verification duration must be between 60 and 600 seconds")
    settings = replace(local_storage_settings(), endpoint=args.endpoint)
    engine = create_engine(local_database_url())
    asset_count = result_count = byte_count = 0
    with Session(engine) as session:
        for revision in session.scalars(
            select(ResourceVersion)
            .join(Resource, Resource.id == ResourceVersion.resource_id)
            .where(Resource.kind == "data")
        ):
            if fingerprint(revision.spec) != revision.checksum:
                raise RuntimeError("Stored data contract checksum mismatch")
            asset = DataAssetSpec.model_validate(revision.spec)
            uri = urlsplit(asset.uri)
            if uri.scheme != "s3":
                raise RuntimeError("Stored data reference is outside S3 verification scope")
            size = asset.quality.get("size_bytes")
            if not isinstance(size, int) or isinstance(size, bool):
                raise RuntimeError("Stored data lacks measured byte count")
            store = S3ArtifactStore(settings, bucket=uri.netloc)
            content = store.read(ArtifactRecord(uri.netloc, uri.path[1:], asset.checksum, size))
            byte_count += len(content)
            asset_count += 1
        for result in session.scalars(select(ResultBundle)):
            if fingerprint(result.manifest) != result.checksum:
                raise RuntimeError("Stored result manifest checksum mismatch")
            bucket, key, checksum, size = (
                result.manifest.get(field) for field in ("bucket", "key", "sha256", "size")
            )
            if (
                not isinstance(bucket, str)
                or not isinstance(key, str)
                or not isinstance(checksum, str)
                or not isinstance(size, int)
                or isinstance(size, bool)
            ):
                raise RuntimeError("Stored result artifact descriptor is invalid")
            record = ArtifactRecord(bucket, key, checksum, size)
            content = S3ArtifactStore(settings, bucket=record.bucket).read(record)
            byte_count += len(content)
            result_count += 1
    engine.dispose()
    if not asset_count or not result_count:
        raise RuntimeError("Verification needs real persisted data and result references")
    print(
        json.dumps(
            {
                "verified_asset_versions": asset_count,
                "verified_results": result_count,
                "verified_bytes": byte_count,
            }
        ),
        flush=True,
    )
    bucket = "coastmas-native-check-" + uuid4().hex
    store = S3ArtifactStore(settings, bucket=bucket)
    store.ensure_bucket()
    started = time.monotonic()

    def write_and_read(index: int) -> ArtifactRecord:
        content = hashlib.sha256(str(index).encode()).digest() * 2048
        record = store.put(f"verification/{index}", content)
        if store.read(record) != content:
            raise RuntimeError("Storage round-trip mismatch")
        return record

    read_count = 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        records = list(pool.map(write_and_read, range(200)))
        read_count += len(records)
        iteration = 0
        while time.monotonic() - started < args.seconds:
            batch = [records[(iteration * 8 + offset) % len(records)] for offset in range(8)]
            list(pool.map(store.read, batch))
            read_count += len(batch)
            with urlopen(args.endpoint + "/minio/health/live", timeout=3) as response:
                if response.status != 200:
                    raise RuntimeError("Object storage health failed")
            time.sleep(0.2)
            iteration += 1
    # This bucket and every deleted key were created by this invocation only.
    import boto3
    from botocore.config import Config

    client = boto3.client(
        "s3",
        endpoint_url=settings.endpoint,
        aws_access_key_id=settings.access_key,
        aws_secret_access_key=settings.secret_key,
        region_name="us-east-1",
        config=Config(connect_timeout=3, read_timeout=10, retries={"total_max_attempts": 1}),
    )
    deleted = client.delete_objects(
        Bucket=bucket, Delete={"Objects": [{"Key": record.key} for record in records]}
    )
    if deleted.get("Errors"):
        raise RuntimeError("Owned verification object cleanup failed")
    client.delete_bucket(Bucket=bucket)
    print(
        json.dumps(
            {
                "status": "PASS",
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "concurrency": 8,
                "verified_writes": len(records),
                "verified_reads": read_count,
                "owned_test_bucket_removed": True,
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
