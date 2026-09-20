"""Shared atomic planning budget and durable provider evidence."""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE planning_traces (
      id varchar(36) PRIMARY KEY, project_id varchar(36) NOT NULL REFERENCES projects(id),
      owner_id varchar(36) NOT NULL REFERENCES users(id), idempotency_key varchar(256) NOT NULL,
      inputs jsonb NOT NULL, fingerprint varchar(64) NOT NULL, allow_external boolean NOT NULL,
      max_provider_requests integer NOT NULL DEFAULT 2
        CHECK (max_provider_requests BETWEEN 0 AND 32),
      reserved_requests integer NOT NULL DEFAULT 0
        CHECK (reserved_requests BETWEEN 0 AND max_provider_requests),
      artifact jsonb, created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(project_id, owner_id, idempotency_key)
    );
    CREATE INDEX ix_planning_traces_project_id ON planning_traces(project_id);
    CREATE TABLE provider_requests (
      id varchar(36) PRIMARY KEY, trace_id varchar(36) NOT NULL REFERENCES planning_traces(id),
      ordinal integer NOT NULL CHECK (ordinal > 0), request_fingerprint varchar(64) NOT NULL,
      status varchar(16) NOT NULL CHECK
        (status IN ('RESERVED','DISPATCHED','SUCCEEDED','INVALID','FAILED')),
      response_fingerprint varchar(64), usage jsonb, error_code varchar(64),
      provider_model varchar(256), provider_endpoint varchar(1024), response_model varchar(256),
      http_status integer CHECK (http_status BETWEEN 100 AND 599),
      created_at timestamptz NOT NULL DEFAULT now(), dispatched_at timestamptz,
      finished_at timestamptz, UNIQUE(trace_id,ordinal)
    );
    CREATE INDEX ix_provider_requests_trace_id ON provider_requests(trace_id);
    CREATE FUNCTION protect_planning_trace() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF ROW(NEW.id,NEW.project_id,NEW.owner_id,NEW.idempotency_key,NEW.inputs,
             NEW.fingerprint,NEW.allow_external,NEW.max_provider_requests,NEW.created_at)
        IS DISTINCT FROM
         ROW(OLD.id,OLD.project_id,OLD.owner_id,OLD.idempotency_key,OLD.inputs,
             OLD.fingerprint,OLD.allow_external,OLD.max_provider_requests,OLD.created_at)
        OR NEW.reserved_requests < OLD.reserved_requests
        OR (OLD.artifact IS NOT NULL AND NEW.artifact IS DISTINCT FROM OLD.artifact) THEN
        RAISE EXCEPTION 'immutable planning identity or monotonic budget violation';
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER protect_planning_trace BEFORE UPDATE ON planning_traces
      FOR EACH ROW EXECUTE FUNCTION protect_planning_trace();
    CREATE FUNCTION protect_provider_request() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF ROW(NEW.id,NEW.trace_id,NEW.ordinal,NEW.request_fingerprint,NEW.created_at,
               NEW.provider_model,NEW.provider_endpoint)
        IS DISTINCT FROM ROW(OLD.id,OLD.trace_id,OLD.ordinal,OLD.request_fingerprint,OLD.created_at,
                             OLD.provider_model,OLD.provider_endpoint)
        OR (OLD.finished_at IS NOT NULL AND NEW IS DISTINCT FROM OLD)
        OR (OLD.dispatched_at IS NOT NULL AND NEW.dispatched_at IS DISTINCT FROM OLD.dispatched_at)
        OR (OLD.status = 'DISPATCHED' AND NEW.status = 'RESERVED') THEN
        RAISE EXCEPTION 'immutable provider evidence violation';
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER protect_provider_request BEFORE UPDATE ON provider_requests
      FOR EACH ROW EXECUTE FUNCTION protect_provider_request();
    """)


def downgrade():
    database = op.get_bind().engine.url.database
    if database is None or not database.startswith("coastmas_test_"):
        raise RuntimeError("Downgrade is restricted to disposable CoastMAS test databases")
    op.execute("""
      DROP TABLE provider_requests;
      DROP TABLE planning_traces;
      DROP FUNCTION protect_provider_request();
      DROP FUNCTION protect_planning_trace();
    """)
