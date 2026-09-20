"""Preserved resource tombstones and immutable dependency records."""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    ALTER TABLE resources ADD COLUMN archived boolean NOT NULL DEFAULT false;
    CREATE INDEX ix_resources_active_project ON resources(project_id,kind) WHERE NOT archived;
    CREATE INDEX ix_resource_dependency_target ON resource_dependencies(target_id,target_version);
    CREATE TRIGGER immutable_resource_dependency BEFORE UPDATE OR DELETE ON resource_dependencies
      FOR EACH ROW EXECUTE FUNCTION reject_immutable_update();
    """)


def downgrade():
    database = op.get_bind().engine.url.database
    if database is None or not database.startswith("coastmas_test_"):
        raise RuntimeError("Downgrade is restricted to disposable CoastMAS test databases")
    op.execute("""
    DROP TRIGGER immutable_resource_dependency ON resource_dependencies;
    DROP INDEX ix_resource_dependency_target;
    DROP INDEX ix_resources_active_project;
    ALTER TABLE resources DROP COLUMN archived;
    """)
