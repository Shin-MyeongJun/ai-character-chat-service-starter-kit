"""Actual PostgreSQL migrations, complete wallet schema parity and history guards."""

import asyncio
import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

ROOT = Path(__file__).resolve().parents[3]
TABLES = (
    "credit_accounts",
    "credit_wallets",
    "credit_balances",
    "credit_transactions",
    "credit_transaction_entries",
    "credit_reservations",
    "billing_quotes",
    "billing_credit_bindings",
)


def migrate_wallets(connection, direction):
    spec = importlib.util.spec_from_file_location(
        "wallet_migration", ROOT / "apps/api/alembic/versions/0024_credit_wallets.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with Operations.context(MigrationContext.configure(connection)):
        getattr(module, direction)()


def full_signature(connection, schema):
    inspector = inspect(connection)

    def normalize(value):
        return str(value).replace(schema + ".", "").replace('"' + schema + '".', "")

    result = {}
    for table in TABLES:
        columns = sorted(
            (c["name"], str(c["type"]), c["nullable"], normalize(c["default"]))
            for c in inspector.get_columns(table, schema=schema)
        )
        foreign = sorted(
            (
                tuple(c["constrained_columns"]),
                c["referred_table"],
                tuple(c["referred_columns"]),
                c["options"].get("ondelete", "NO ACTION"),
            )
            for c in inspector.get_foreign_keys(table, schema=schema)
        )
        unique = sorted(
            tuple(c["column_names"])
            for c in inspector.get_unique_constraints(table, schema=schema)
        )
        checks = sorted(
            c["sqltext"] for c in inspector.get_check_constraints(table, schema=schema)
        )
        indexes = sorted(
            (
                tuple(c["column_names"]),
                c["unique"],
                normalize(c.get("dialect_options", {})),
            )
            for c in inspector.get_indexes(table, schema=schema)
        )
        primary = inspector.get_pk_constraint(table, schema=schema)[
            "constrained_columns"
        ]
        result[table] = (columns, foreign, unique, checks, indexes, primary)
    return result


@pytest.mark.asyncio
async def test_full_online_alembic_initial_sql_and_orm_match_every_wallet_constraint(
    db,
):
    url = make_url(os.environ["TEST_DATABASE_URL"])
    # Dedicated child database, never an application's configured DATABASE_URL.
    name = "credit_schema_test_" + uuid4().hex
    admin = await asyncpg.connect(
        url.set(drivername="postgresql").render_as_string(hide_password=False)
    )
    await admin.execute(f'CREATE DATABASE "{name}"')
    connection = None
    try:
        env = dict(
            os.environ,
            DATABASE_URL=url.set(database=name).render_as_string(hide_password=False),
        )
        await asyncio.to_thread(
            subprocess.check_output,
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                str(ROOT / "apps/api/alembic.ini"),
                "upgrade",
                "head",
            ],
            cwd=ROOT,
            env=env,
            stderr=subprocess.STDOUT,
        )
        connection = await asyncpg.connect(
            url.set(drivername="postgresql", database=name).render_as_string(
                hide_password=False
            )
        )
        assert (
            await connection.fetchval("SELECT version_num FROM alembic_version")
            == "0024"
        )
        await connection.execute("CREATE SCHEMA initial")
        await connection.execute("SET search_path TO initial,public")
        async with connection.transaction():
            for path in sorted((ROOT / "infra/postgres/init").glob("*.sql")):
                await connection.execute(path.read_text(encoding="utf-8-sig"))
        from sqlalchemy.ext.asyncio import create_async_engine

        engine = create_async_engine(url.set(database=name))
        try:
            async with db.bind.connect() as conn:
                source = await conn.scalar(text("SELECT current_schema()"))
                expected = await conn.run_sync(full_signature, source)
            async with engine.connect() as conn:
                for schema in ("public", "initial"):
                    actual = await conn.run_sync(full_signature, schema)
                    assert actual == expected, {
                        t: (actual[t], expected[t])
                        for t in TABLES
                        if actual[t] != expected[t]
                    }
            # Exercise the final services on both migrated and initial SQL databases.
            from app.db.models.identity import User
            from app.modules.commerce.credit import types as CreditTypes
            from app.modules.commerce.credit.service import command as CreditCommands
            from app.modules.commerce.credit.service import query as CreditQueries
            from sqlalchemy.ext.asyncio import AsyncSession
            from test_credit_wallets import finalize, grant, reserve

            for schema in ("public", "initial"):
                async with engine.begin() as conn:
                    await conn.execute(
                        text(f"SET LOCAL search_path TO {schema},public")
                    )
                    async with AsyncSession(
                        bind=conn, expire_on_commit=False
                    ) as session:
                        async with session.begin():
                            uid = uuid4()
                            session.add(User(id=uid, email=f"{uid}@migrated.test"))
                            await session.flush()
                            await CreditCommands.grant_credit(session, grant(uid, 30))
                            await CreditCommands.grant_credit(
                                session, grant(uid, 70, CreditTypes.CreditBucket.PAID)
                            )
                            reservation = await CreditCommands.reserve_credit(
                                session, reserve(uid, 50)
                            )
                            assert (
                                reservation.free_amount,
                                reservation.paid_amount,
                            ) == (30, 20)
                            await CreditCommands.commit_credit_reservation(
                                session, finalize(reservation)
                            )
                            info = await CreditQueries.get_credit_balance(
                                session,
                                CreditTypes.GetCreditBalanceCommand(
                                    user_id=uid, currency_code="CREDIT"
                                ),
                            )
                            assert (
                                info.free.balance_credit,
                                info.paid.balance_credit,
                            ) == (0, 50)
        finally:
            await engine.dispose()
    finally:
        if connection is not None:
            await connection.close()
        await admin.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
        await admin.close()


async def historical_schema(conn, revision="0023"):
    name = "wallet_history_" + uuid4().hex
    await conn.execute(text(f"CREATE SCHEMA {name}"))
    await conn.execute(text(f"SET LOCAL search_path TO {name},public"))
    sql = await asyncio.to_thread(
        subprocess.check_output,
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(ROOT / "apps/api/alembic.ini"),
            "upgrade",
            revision,
            "--sql",
        ],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
    )
    raw = await conn.get_raw_connection()
    await raw.driver_connection.execute(
        sql.replace("BEGIN;", "").replace("COMMIT;", "")
    )
    return name


@pytest.mark.asyncio
async def test_wallet_upgrade_preserves_legacy_and_safe_empty_downgrade(db):
    async with db.bind.begin() as conn:
        schema = await historical_schema(conn)
        uid, tid = uuid4(), uuid4()
        await conn.execute(
            text("INSERT INTO users(id,email) VALUES (:u,'migration@wallet.test')"),
            {"u": uid},
        )
        await conn.execute(
            text("INSERT INTO credit_accounts(user_id,balance) VALUES (:u,37)"),
            {"u": uid},
        )
        await conn.execute(
            text(
                "INSERT INTO "
                "credit_transactions(id,user_id,amount,reason,idempotency_key) "
                "VALUES (:t,:u,37,'purchase','untouched')"
            ),
            {"u": uid, "t": tid},
        )
        account = dict(
            (await conn.execute(text("SELECT * FROM credit_accounts"))).mappings().one()
        )
        ledger = dict(
            (await conn.execute(text("SELECT * FROM credit_transactions")))
            .mappings()
            .one()
        )
        await conn.run_sync(migrate_wallets, "upgrade")
        assert (
            dict(
                (await conn.execute(text("SELECT * FROM credit_accounts")))
                .mappings()
                .one()
            )
            == account
        )
        after = dict(
            (
                await conn.execute(
                    text(
                        "SELECT *, operation AS checked_operation FROM "
                        "credit_transactions"
                    )
                )
            )
            .mappings()
            .one()
        )
        assert {k: after[k] for k in ledger} == ledger
        assert after["operation"] == "legacy" and after["currency_code"] is None
        assert await conn.scalar(text("SELECT count(*) FROM credit_wallets")) == 0
        await conn.run_sync(migrate_wallets, "downgrade")
        assert (
            dict(
                (
                    await conn.execute(
                        text(
                            "SELECT "
                            "id,user_id,amount,reason,reference_id,"
                            "idempotency_key,created_at "
                            "FROM credit_transactions"
                        )
                    )
                )
                .mappings()
                .one()
            )
            == ledger
        )
        await conn.run_sync(migrate_wallets, "upgrade")
        await conn.execute(
            text(
                "INSERT INTO credit_wallets(user_id,currency_code) VALUES (:u,'CREDIT')"
            ),
            {"u": uid},
        )
        with pytest.raises(DBAPIError, match="Preserve classified credit history"):
            async with conn.begin_nested():
                await conn.run_sync(migrate_wallets, "downgrade")
        assert await conn.scalar(text("SELECT count(*) FROM credit_wallets")) == 1
        await conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))


@pytest.mark.asyncio
async def test_wallet_migration_failure_rolls_back_all_ddl(db):
    async with db.bind.begin() as conn:
        schema = await historical_schema(conn)
        # Force a late failure after wallet creation and reservation ALTERs.
        await conn.execute(
            text("CREATE TABLE credit_transaction_entries (sentinel integer)")
        )
        before = await conn.run_sync(
            lambda c: inspect(c).get_columns("credit_transactions", schema=schema)
        )
        with pytest.raises(DBAPIError):
            async with conn.begin_nested():
                await conn.run_sync(migrate_wallets, "upgrade")
        after = await conn.run_sync(
            lambda c: inspect(c).get_columns("credit_transactions", schema=schema)
        )
        assert [(c["name"], str(c["type"])) for c in after] == [
            (c["name"], str(c["type"])) for c in before
        ]
        assert not await conn.run_sync(
            lambda c: inspect(c).has_table("credit_wallets", schema=schema)
        )
        assert await conn.run_sync(
            lambda c: inspect(c).has_table("credit_transaction_entries", schema=schema)
        )
        await conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))
