"""Disk transfers must exceed the legacy memory budget without unbounded reads."""

import hashlib

import pytest

from coastmas.adapters.storage import ArtifactRecord
from coastmas.core.errors import CoastMASError


def test_file_transfer_above_memory_budget_is_verified_and_immutable(storage, tmp_path):
    source = tmp_path / "source.bin"
    payload = b"science-zero\x00" * 10000
    source.write_bytes(payload)
    storage.max_bytes = 1024
    record = storage.put_file("project/data/object", source, max_bytes=200000)
    assert record.size == len(payload)
    assert record.sha256 == hashlib.sha256(payload).hexdigest()
    downloaded = tmp_path / "download.bin"
    storage.read_file(record, downloaded, max_bytes=200000)
    assert downloaded.read_bytes() == payload
    assert storage.put_file(record.key, source, max_bytes=200000) == record
    source.write_bytes(b"different")
    with pytest.raises(CoastMASError, match="immutable"):
        storage.put_file(record.key, source, max_bytes=200000)
    assert source.read_bytes() == b"different"


def test_transfer_limits_and_checksum_failures_leave_no_partial_file(storage, tmp_path):
    source = tmp_path / "source.bin"
    source.write_bytes(b"0123456789")
    with pytest.raises(CoastMASError):
        storage.put_file("project/large", source, max_bytes=5)
    record = storage.put("project/valid", b"0123456789")
    target = tmp_path / "download.bin"
    forged = ArtifactRecord(record.bucket, record.key, "0" * 64, record.size)
    with pytest.raises(CoastMASError):
        storage.read_file(forged, target, max_bytes=20)
    assert not target.exists()
    target.write_bytes(b"existing")
    with pytest.raises(FileExistsError):
        storage.read_file(record, target, max_bytes=20)
    assert target.read_bytes() == b"existing"
