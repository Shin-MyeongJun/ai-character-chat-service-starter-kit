import asyncio
import os

import app.db.models  # noqa: F401
from alembic import context
from app.db.base import Base
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine


def migrate(connection):
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()


async def online():
    engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=pool.NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(migrate)
    await engine.dispose()


if context.is_offline_mode():
    context.configure(url="postgresql://", literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(online())
