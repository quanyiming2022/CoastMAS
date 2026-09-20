import pytest

from coastmas.core.errors import CoastMASError


def test_real_object_store_is_immutable_and_checksum_verified(storage):
    artifact = storage.put("project/job/result.json", b'{"value":42}')
    assert storage.read(artifact) == b'{"value":42}'
    assert storage.put("project/job/result.json", b'{"value":42}') == artifact
    with pytest.raises(CoastMASError, match="immutable"):
        storage.put("project/job/result.json", b'{"value":99}')
    assert storage.read(artifact) == b'{"value":42}'


def test_object_keys_cannot_escape_namespace(storage):
    for key in ("../secret", "/absolute", "a/../../escape", "a\\b"):
        with pytest.raises(CoastMASError):
            storage.put(key, b"data")
