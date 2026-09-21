from scripts.evidence import redact_secrets


def test_failure_evidence_redacts_credentials_without_hiding_error():
    raw = "connection failed password=secret-123! host=localhost\nexit code 1\npostgresql://u:secret-123%21@host/db"
    sanitized = redact_secrets(raw, ["secret-123!"])
    assert "secret-123" not in sanitized
    assert "connection failed" in sanitized
    assert "exit code 1" in sanitized
    assert sanitized.count("[REDACTED]") == 2


def test_no_secret_never_changes_scientific_diagnostics():
    raw = "CONSTRAINT_ERROR: datum mismatch\n1 failed, 2 passed\n"
    assert redact_secrets(raw, []) == raw


def test_numeric_output_budget_is_not_a_credential_but_access_token_is(monkeypatch):
    from scripts.evidence import configured_secrets

    monkeypatch.setenv("LLM_MAX_COMPLETION_TOKENS", "21637")
    monkeypatch.setenv("COASTMAS_ACCESS_TOKEN", "private-access-token-example")
    values = configured_secrets()
    assert "21637" not in values
    assert "private-access-token-example" in values
