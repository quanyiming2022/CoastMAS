from alembic import context
from sqlalchemy import create_engine

from coastmas.persistence.database import local_database_url
from coastmas.persistence.schema import Base

configuration = context.config
engine = configuration.attributes.get("engine")
if engine is None:
    engine = create_engine(local_database_url())
if context.is_offline_mode():
    raise RuntimeError("Offline migration is unsupported; use a project database")
with engine.connect() as connection:
    if configuration.cmd_opts is not None and getattr(configuration.cmd_opts, "cmd", None):
        operation = configuration.cmd_opts.cmd[0].__name__
        if operation == "downgrade" and not engine.url.database.startswith("coastmas_test_"):
            raise RuntimeError("Downgrade allowed only in a disposable CoastMAS test database")
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()
