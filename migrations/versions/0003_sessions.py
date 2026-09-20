"""Opaque revocable browser sessions."""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE auth_sessions (
        token_hash varchar(64) PRIMARY KEY, user_id varchar(36) NOT NULL REFERENCES users(id),
        csrf_hash varchar(64) NOT NULL, expires_at timestamptz NOT NULL);
        CREATE INDEX ix_auth_sessions_user_id ON auth_sessions(user_id);
    """)


def downgrade():
    database = op.get_bind().engine.url.database
    if database is None or not database.startswith("coastmas_test_"):
        raise RuntimeError("Downgrade is restricted to disposable CoastMAS test databases")
    op.execute("DROP TABLE auth_sessions")
