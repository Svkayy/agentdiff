import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from server.config import get_settings
from server.db import Base
import server.models  # noqa: F401  (register all tables on Base.metadata)

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)
target_metadata = Base.metadata


def _do_run_migrations(connection) -> None:
    # Configure AND run inside ONE sync execution, wrapped in a transaction, so
    # the DDL (and the alembic_version bump) is actually committed. Splitting
    # configure/run across two separate run_sync calls, with no begin_transaction,
    # silently no-ops the migration: alembic logs "Running upgrade" but nothing
    # is persisted.
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = create_async_engine(get_settings().database_url)
    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await connectable.dispose()


asyncio.run(run_migrations_online())
