from coastmas_next.config import Settings


def test_settings_repr_does_not_expose_database_credentials(tmp_path):
    secret = "fixture-secret-not-for-logs"
    settings = Settings(
        database_url=f"postgresql+psycopg://test:{secret}@localhost/coastmas_next_fixture",
        storage_root=tmp_path,
    )
    assert secret not in repr(settings)
