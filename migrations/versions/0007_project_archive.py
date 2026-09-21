"""Recoverable project visibility; immutable scientific records are untouched."""

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE projects ADD COLUMN archived boolean NOT NULL DEFAULT false")


def downgrade():
    op.execute("ALTER TABLE projects DROP COLUMN archived")
