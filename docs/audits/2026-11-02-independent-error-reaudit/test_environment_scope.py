"""Read-only final check, invoked only through the guarded PG audit runner."""

import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.mark.asyncio
async def test_dedicated_database_state_after_audit():
    for label, key in (("application-test", "TEST_DATABASE_URL"), ("identity-test", "TEST_AUTH_DATABASE_URL")):
        engine = create_async_engine(os.environ[key])
        try:
            async with engine.connect() as connection:
                version = await connection.scalar(text("SHOW server_version"))
                isolation = await connection.scalar(text("SHOW transaction_isolation"))
                leftovers = await connection.scalar(text(
                    "SELECT count(*) FROM pg_namespace "
                    "WHERE nspname ~ '^(test_|auth_test_|audit_|u[0-9]+_)'"
                ))
                print(f"ENVIRONMENT label={label} version={version} isolation={isolation} matching_test_schemas={leftovers}")
                assert leftovers == 0, "Audit test schemas remain; do not delete without identifying ownership"
        finally:
            await engine.dispose()
