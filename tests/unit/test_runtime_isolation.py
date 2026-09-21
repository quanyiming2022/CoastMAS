from coastmas.persistence.database import local_database_url
from coastmas.runtime_bootstrap import configured_provider


def test_selected_database_never_leaks_into_explicit_test_database(monkeypatch):
    monkeypatch.setenv("POSTGRES_PASSWORD", "unit-test-only")
    monkeypatch.setenv("POSTGRES_DB", "coastmas_e2e_unique")
    assert local_database_url().database == "coastmas_e2e_unique"
    assert local_database_url("coastmas_test_other").database == "coastmas_test_other"


def test_disabled_provider_does_not_read_or_use_available_credentials(monkeypatch):
    monkeypatch.setenv("COASTMAS_LLM_ENABLED", "false")
    monkeypatch.setenv("LLM_API_KEY", "unit-test-only")
    monkeypatch.setenv("LLM_MODEL", "local-test")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.invalid/v1")
    assert configured_provider() is None
