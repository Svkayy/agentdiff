import asyncio
from logging.config import fileConfig
from sqlalchemy.ext.asyncio import create_async_engine
from alembic import context
from server.config import get_settings
from server.db import Base
import server.models  # noqa: F401

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)
target_metadata = Base.metadata


def run_migrations_online():
    connectable = create_async_engine(get_settings().database_url)

    async def do_run():
        async with connectable.connect() as conn:
            await conn.run_sync(lambda c: context.configure(connection=c, target_metadata=target_metadata))
            await conn.run_sync(lambda _: context.run_migrations())

    asyncio.run(do_run())


run_migrations_online()
