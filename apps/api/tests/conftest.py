import os
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.db.base import Base
import app.db.models  # noqa: F401


@pytest_asyncio.fixture
async def db():
    url = os.getenv('TEST_DATABASE_URL')
    if not url:
        pytest.skip('TEST_DATABASE_URL required for PostgreSQL integration tests')
    if 'test' not in url.rsplit('/', 1)[-1]:
        raise RuntimeError('Integration tests require a database with test in its name.')
    schema = 'test_' + uuid4().hex
    engine = create_async_engine(url, connect_args={'server_settings': {'search_path': f'{schema},public'}})
    async with engine.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA {schema}'))
        await connection.run_sync(Base.metadata.create_all)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            yield session
    finally:
        async with engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA {schema} CASCADE'))
        await engine.dispose()
