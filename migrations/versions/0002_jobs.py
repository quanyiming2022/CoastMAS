"""Job idempotency, leases and immutable published bundles."""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE jobs (
        id varchar(36) PRIMARY KEY, project_id varchar(36) NOT NULL REFERENCES projects(id),
        submitted_by varchar(36) NOT NULL REFERENCES users(id),
        idempotency_key varchar(256) NOT NULL, fingerprint varchar(64) NOT NULL,
        manifest jsonb NOT NULL CHECK(jsonb_typeof(manifest)='object'),
        status varchar(16) NOT NULL DEFAULT 'QUEUED'
            CHECK(status IN ('QUEUED','RUNNING','SUCCEEDED','FAILED','CANCELLED')),
        cancel_requested boolean NOT NULL DEFAULT false, worker_token varchar(36),
        lease_until timestamptz, attempt integer NOT NULL DEFAULT 0 CHECK(attempt>=0),
        progress double precision NOT NULL DEFAULT 0 CHECK(progress>=0 AND progress<=1),
        error jsonb, created_at timestamptz NOT NULL DEFAULT now(),
        started_at timestamptz, finished_at timestamptz,
        UNIQUE(project_id,submitted_by,idempotency_key)
    );
    CREATE INDEX ix_jobs_project_id ON jobs(project_id);
    CREATE INDEX ix_jobs_dispatch ON jobs(status,lease_until);
    CREATE TABLE result_bundles (
        id varchar(36) PRIMARY KEY, job_id varchar(36) NOT NULL UNIQUE REFERENCES jobs(id),
        manifest jsonb NOT NULL CHECK(jsonb_typeof(manifest)='object'),
        checksum varchar(64) NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE TRIGGER immutable_result_bundle BEFORE UPDATE OR DELETE ON result_bundles
      FOR EACH ROW EXECUTE FUNCTION reject_immutable_update();
    CREATE FUNCTION enforce_job_transition() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF NEW.manifest IS DISTINCT FROM OLD.manifest
         OR NEW.fingerprint IS DISTINCT FROM OLD.fingerprint
         OR NEW.submitted_by IS DISTINCT FROM OLD.submitted_by
         OR NEW.project_id IS DISTINCT FROM OLD.project_id
         OR NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key THEN
        RAISE EXCEPTION 'job input identity is immutable';
      END IF;
      IF OLD.status IN ('SUCCEEDED','FAILED','CANCELLED') AND NEW IS DISTINCT FROM OLD THEN
        RAISE EXCEPTION 'terminal job is immutable';
      END IF;
      IF NEW.status <> OLD.status AND NOT (
        (OLD.status='QUEUED' AND NEW.status IN ('RUNNING','CANCELLED','FAILED')) OR
        (OLD.status='RUNNING' AND NEW.status IN ('SUCCEEDED','FAILED','CANCELLED'))
      ) THEN RAISE EXCEPTION 'invalid job state transition'; END IF;
      RETURN NEW;
    END;
    $$;
    CREATE TRIGGER job_transition BEFORE UPDATE ON jobs
      FOR EACH ROW EXECUTE FUNCTION enforce_job_transition();
    """)


def downgrade():
    database = op.get_bind().engine.url.database
    if database is None or not database.startswith("coastmas_test_"):
        raise RuntimeError("Downgrade is restricted to disposable CoastMAS test databases")
    op.execute(
        "DROP TABLE result_bundles; DROP TABLE jobs; DROP FUNCTION enforce_job_transition();"
    )
