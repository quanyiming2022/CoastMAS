"""Immutable spatial materializations bound to scientific resource versions."""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE geographic_entities (
      resource_id varchar(256) NOT NULL,
      version integer NOT NULL CHECK (version > 0),
      geometry geometry(Geometry,4326) NOT NULL,
      valid_from timestamptz NOT NULL,
      valid_to timestamptz,
      PRIMARY KEY(resource_id,version),
      FOREIGN KEY(resource_id,version) REFERENCES resource_versions(resource_id,version),
      CHECK(valid_to IS NULL OR valid_to > valid_from),
      CHECK(NOT ST_IsEmpty(geometry) AND ST_IsValid(geometry)),
      CHECK(ST_NPoints(geometry) <= 100000)
    );
    CREATE INDEX ix_geographic_entities_geometry ON geographic_entities USING gist(geometry);
    CREATE TRIGGER immutable_geographic_entity BEFORE UPDATE OR DELETE ON geographic_entities
      FOR EACH ROW EXECUTE FUNCTION reject_immutable_update();
    """)


def downgrade():
    op.execute("DROP TABLE geographic_entities")
