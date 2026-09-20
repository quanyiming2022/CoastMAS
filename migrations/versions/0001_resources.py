"""Project authorization and immutable contract storage.

Revision ID: 0001
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("""
    CREATE TABLE users (
        id varchar(36) PRIMARY KEY, email varchar(320) NOT NULL UNIQUE,
        password_hash varchar(256) NOT NULL, active boolean NOT NULL DEFAULT true,
        is_admin boolean NOT NULL DEFAULT false
    );
    CREATE TABLE projects (
        id varchar(36) PRIMARY KEY, name varchar(256) NOT NULL,
        owner_id varchar(36) NOT NULL REFERENCES users(id)
    );
    CREATE TABLE project_memberships (
        project_id varchar(36) REFERENCES projects(id), user_id varchar(36) REFERENCES users(id),
        role varchar(16) NOT NULL CHECK(role IN ('ADMIN','RESEARCHER','MANAGER','VIEWER','PUBLIC')),
        PRIMARY KEY(project_id,user_id)
    );
    CREATE TABLE resources (
        id varchar(256) PRIMARY KEY, project_id varchar(36) NOT NULL REFERENCES projects(id),
        kind varchar(32) NOT NULL, name varchar(256) NOT NULL,
        owner_id varchar(36) NOT NULL REFERENCES users(id),
        current_version integer NOT NULL CHECK(current_version > 0),
        enabled boolean NOT NULL DEFAULT true, published boolean NOT NULL DEFAULT false
    );
    CREATE INDEX ix_resources_project_id ON resources(project_id);
    CREATE INDEX ix_resources_kind ON resources(kind);
    CREATE TABLE resource_versions (
        resource_id varchar(256) REFERENCES resources(id), version integer CHECK(version > 0),
        spec jsonb NOT NULL CHECK(jsonb_typeof(spec)='object'),
        checksum varchar(64) NOT NULL CHECK(checksum ~ '^[a-f0-9]{64}$'),
        created_by varchar(36) NOT NULL REFERENCES users(id),
        created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(resource_id,version)
    );
    ALTER TABLE resources ADD CONSTRAINT resource_current_version_fk
      FOREIGN KEY(id,current_version) REFERENCES resource_versions(resource_id,version)
      DEFERRABLE INITIALLY DEFERRED;
    CREATE TABLE resource_dependencies (
        source_id varchar(256), source_version integer,
        target_id varchar(256), target_version integer,
        PRIMARY KEY(source_id,source_version,target_id,target_version),
        FOREIGN KEY(source_id,source_version) REFERENCES resource_versions(resource_id,version),
        FOREIGN KEY(target_id,target_version) REFERENCES resource_versions(resource_id,version)
    );
    CREATE TABLE audit_logs (
        id varchar(36) PRIMARY KEY, who varchar(36) NOT NULL REFERENCES users(id),
        "when" timestamptz NOT NULL DEFAULT now(), action varchar(32) NOT NULL,
        resource varchar(256) NOT NULL, old_value jsonb, new_value jsonb
    );
    CREATE FUNCTION reject_immutable_update() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN RAISE EXCEPTION 'immutable scientific revision or audit entry'; END;
    $$;
    CREATE TRIGGER immutable_resource_version BEFORE UPDATE OR DELETE ON resource_versions
      FOR EACH ROW EXECUTE FUNCTION reject_immutable_update();
    CREATE TRIGGER immutable_audit BEFORE UPDATE OR DELETE ON audit_logs
      FOR EACH ROW EXECUTE FUNCTION reject_immutable_update();
    """)


def downgrade():
    database = op.get_bind().engine.url.database
    if database is None or not database.startswith("coastmas_test_"):
        raise RuntimeError("Downgrade is restricted to disposable CoastMAS test databases")
    op.execute("""
    DROP TABLE audit_logs;
    DROP TABLE resource_dependencies;
    ALTER TABLE resources DROP CONSTRAINT resource_current_version_fk;
    DROP TABLE resource_versions;
    DROP TABLE resources;
    DROP TABLE project_memberships;
    DROP TABLE projects;
    DROP TABLE users;
    DROP FUNCTION reject_immutable_update();
    """)
