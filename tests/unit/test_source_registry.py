import json

import pytest

from coastmas.adapters.source_registry import load_sources


def test_source_config_resolves_secrets_only_from_environment(tmp_path, monkeypatch):
    path = tmp_path / "sources.json"
    path.write_text(
        json.dumps(
            {
                "observations": {
                    "kind": "http",
                    "name": "Observations",
                    "revision": 1,
                    "projects": ["project"],
                    "url": "https://example.invalid/data.csv",
                    "headers_env": {"Authorization": "COASTMAS_SOURCE_TEST_AUTH"},
                }
            }
        )
    )
    path.chmod(0o600)
    monkeypatch.setenv("COASTMAS_SOURCE_TEST_AUTH", "Bearer private-test-credential")
    registered = load_sources(path)["observations"]
    assert registered.source.headers["Authorization"] == "Bearer private-test-credential"
    assert registered.projects == frozenset({"project"})
    assert "private-test-credential" not in repr(registered)
    assert load_sources(None) == {}


def test_source_config_rejects_duplicate_keys_and_unprotected_files(tmp_path):
    path = tmp_path / "sources.json"
    path.write_text('{"same":{},"same":{}}')
    path.chmod(0o600)
    with pytest.raises(RuntimeError, match="configuration"):
        load_sources(path)
    path.write_text("{}")
    path.chmod(0o644)
    with pytest.raises(RuntimeError, match="permissions"):
        load_sources(path)


def test_source_config_failure_does_not_echo_sensitive_input(tmp_path):
    path = tmp_path / "sources.json"
    secret = "embedded-private-input"
    path.write_text(json.dumps({"broken": {"kind": "postgresql", "dsn": secret}}))
    path.chmod(0o600)
    with pytest.raises(RuntimeError) as error:
        load_sources(path)
    assert secret not in str(error.value)
