"""0023 retains historical values and replays billing contracts after migration."""

import importlib.util
import sys
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from app.modules.commerce.billing import types as BillingTypes
from app.modules.commerce.billing.service import credits as BillingCreditService
from app.modules.commerce.billing.service import quotes as QuoteService
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession
from test_billing_credits import NOW, _credit_fixture  # noqa: F401
from test_billing_prices import _configuration, _request_info  # noqa: F401

ROOT = Path(__file__).resolve().parents[3]
TABLES = (
    "credit_accounts",
    "credit_transactions",
    "credit_reservations",
    "billing_quotes",
    "billing_credit_bindings",
)


def _migrate(connection, direction):
    spec = importlib.util.spec_from_file_location(
        "credit_ownership_migration",
        ROOT / "apps/api/alembic/versions/0023_credit_ownership.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with Operations.context(MigrationContext.configure(connection)):
        getattr(module, direction)()


async def _create_legacy_schema(conn, source, schema):
    await conn.execute(text(f"CREATE SCHEMA {schema}"))
    await conn.execute(text(f"SET LOCAL search_path TO {schema}, public"))
    # Frozen historical DDL through 0021, copied users/quotes only.
    import asyncio
    import subprocess

    sql = await asyncio.to_thread(
        subprocess.check_output,
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(ROOT / "apps/api/alembic.ini"),
            "upgrade",
            "0021",
            "--sql",
        ],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
    )
    import asyncpg

    # The current SQLAlchemy connection must own the DDL transaction.
    raw = await conn.get_raw_connection()
    driver: asyncpg.Connection = raw.driver_connection
    sql = sql.replace("BEGIN;", "").replace("COMMIT;", "")
    await driver.execute(sql)
    for table in ("users", "billing_quotes"):
        columns = await conn.run_sync(
            lambda c: inspect(c).get_columns(table, schema=schema)
        )
        projection = ", ".join('"' + c["name"] + '"' for c in columns)
        await conn.execute(
            text(
                f"INSERT INTO {table} ({projection}) "
                f"SELECT {projection} FROM {source}.{table}"
            )
        )
    await conn.execute(
        text("INSERT INTO credit_accounts(user_id,balance) SELECT id,20 FROM users")
    )
    sql = (ROOT / "infra/postgres/init/013_billing_credits.sql").read_text(
        encoding="utf-8"
    )
    for statement in sql.split(";"):
        if statement.strip():
            await conn.execute(text(statement))


def _constraints(connection, schema):
    inspector = inspect(connection)
    return {
        table: (
            inspector.get_check_constraints(table, schema=schema),
            sorted(
                (tuple(index["column_names"]), index["unique"])
                for index in inspector.get_indexes(table, schema=schema)
            ),
            sorted(
                (col["name"], col["default"])
                for col in inspector.get_columns(table, schema=schema)
            ),
        )
        for table in TABLES
    }


async def _rows(conn, table):
    columns = await conn.run_sync(lambda c: inspect(c).get_columns(table))
    projection = ", ".join('"' + column["name"] + '"' for column in columns)
    return [
        dict(row)
        for row in (
            await conn.execute(text(f"SELECT {projection} FROM {table} ORDER BY 1"))
        ).mappings()
    ]


@pytest.mark.asyncio
async def test_online_ownership_preserves_all_values_and_billing_replays(
    db, credit_fixture, configuration
):
    commands = [credit_fixture]
    for _ in range(2):
        request = replace(credit_fixture.request, request_key=uuid4())
        quote = await QuoteService.create_billing_quote(
            db,
            BillingTypes.CreateBillingQuoteCommand(request=request),
            configuration=configuration,
            clock=lambda: NOW,
        )
        commands.append(
            replace(
                credit_fixture,
                request_key=request.request_key,
                request=request,
                quote_id=quote.id,
            )
        )
    schema = "ownership_" + uuid4().hex
    async with db.bind.begin() as conn:
        source = await conn.scalar(text("SELECT current_schema()"))
        await _create_legacy_schema(conn, source, schema)
        try:
            rid, tid = uuid4(), uuid4()
            records = []
            for status, command in zip(
                ("reserved", "committed", "released"), commands, strict=True
            ):
                reservation_id = uuid4()
                if status == "committed":
                    await conn.execute(
                        text(
                            "INSERT INTO "
                            "credit_transactions(id,user_id,amount,reason,"
                            "reference_id,idempotency_key) "
                            "VALUES "
                            "(:tid,:uid,-10,'chat_usage',:rid,'historical-settlement-key')"
                        ),
                        {"tid": tid, "uid": command.user_id, "rid": rid},
                    )
                await conn.execute(
                    text(
                        "INSERT INTO "
                        "credit_reservations(id,user_id,request_key,quote_id,status,"
                        "reserved_credit,result_id,transaction_id,"
                        "created_at,finalized_at) "
                        "VALUES (:id,:uid,:key,:qid,:status,10,:rid,:tid,:now,:final)"
                    ),
                    {
                        "id": reservation_id,
                        "uid": command.user_id,
                        "key": command.request_key,
                        "qid": command.quote_id,
                        "status": status,
                        "rid": rid if status == "committed" else None,
                        "tid": tid if status == "committed" else None,
                        "now": NOW,
                        "final": None if status == "reserved" else NOW,
                    },
                )
                records.append(
                    BillingTypes.CreditReservationInfo(
                        id=reservation_id,
                        user_id=command.user_id,
                        request_key=command.request_key,
                        quote_id=command.quote_id,
                        status=BillingTypes.CreditReservationStatus(status),
                        reserved_credit=10,
                        result_id=rid if status == "committed" else None,
                    )
                )
            await conn.execute(
                text("UPDATE credit_accounts SET balance=10,reserved_credit=10")
            )
            before = {table: await _rows(conn, table) for table in TABLES[:-1]}
            await conn.run_sync(_migrate, "upgrade")
            for table in ("credit_accounts", "credit_transactions", "billing_quotes"):
                assert await _rows(conn, table) == before[table]
            after = await _rows(conn, "credit_reservations")
            bindings = {
                row["reservation_id"]: row
                for row in await _rows(conn, "billing_credit_bindings")
            }
            for old, new in zip(before["credit_reservations"], after, strict=True):
                assert {key: new[key] for key in old if key != "quote_id"} == {
                    key: value for key, value in old.items() if key != "quote_id"
                }
                assert bindings[old["id"]]["quote_id"] == old["quote_id"]
                assert bindings[old["id"]]["created_at"] == old["created_at"]
                assert new["reference_id"] == old["id"]
                if new["status"] == "committed":
                    assert new["settlement_key"] == "historical-settlement-key"
            # 0024 preserves unclassified reservations, then the new runtime blocks
            # their activation rather than inventing a free/paid allocation.
            from test_credit_wallet_migrations import migrate_wallets

            await conn.run_sync(migrate_wallets, "upgrade")
            from app.modules.commerce.credit import types as CreditTypes
            from app.modules.commerce.credit.service import query as CreditQueryService

            async with AsyncSession(bind=conn, expire_on_commit=False) as session:
                for command in commands:
                    with pytest.raises(BillingTypes.CreditAccountNotFoundError):
                        async with session.begin_nested():
                            await BillingCreditService.reserve_credit(
                                session, command, clock=lambda: NOW
                            )
                history = await CreditQueryService.list_credit_reservations(
                    session,
                    CreditTypes.ListCreditReservationsCommand(
                        user_id=commands[0].user_id, currency_code=None
                    ),
                )
                assert len(history.items) == 3
                assert all(
                    r.free_amount is None and r.paid_amount is None
                    for r in history.items
                )
            assert await conn.scalar(text("SELECT balance FROM credit_accounts")) == 10
            for table in ("credit_accounts", "billing_quotes"):
                assert await _rows(conn, table) == before[table]
            with pytest.raises(DBAPIError, match="Preserve credit ownership history"):
                async with conn.begin_nested():
                    await conn.run_sync(_migrate, "downgrade")
        finally:
            # Failed outer transactions roll back CREATE SCHEMA as well.
            if sys.exc_info()[0] is None:
                await conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))


@pytest.mark.asyncio
async def test_empty_ownership_downgrade_and_opaque_reason_guard(db):
    schema = "ownership_" + uuid4().hex
    async with db.bind.begin() as conn:
        source = await conn.scalar(text("SELECT current_schema()"))
        await _create_legacy_schema(conn, source, schema)
        try:
            await conn.run_sync(_migrate, "upgrade")
            await conn.run_sync(_migrate, "downgrade")
            await conn.run_sync(_migrate, "upgrade")
            uid = uuid4()
            await conn.execute(
                text("INSERT INTO users(id,email) VALUES (:uid,'opaque@credit.test')"),
                {"uid": uid},
            )
            await conn.execute(
                text(
                    "INSERT INTO "
                    "credit_transactions(user_id,amount,reason,idempotency_key) "
                    "VALUES (:uid,0,'export','opaque-key')"
                ),
                {"uid": uid},
            )
            with pytest.raises(DBAPIError, match="Preserve credit ownership history"):
                async with conn.begin_nested():
                    await conn.run_sync(_migrate, "downgrade")
        finally:
            # Failed outer transactions roll back CREATE SCHEMA as well.
            if sys.exc_info()[0] is None:
                await conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "corruption", ["quote_identity", "ledger_amount", "settlement_key"]
)
async def test_invalid_legacy_history_aborts_without_partial_migration(
    db, credit_fixture, corruption
):
    schema = "ownership_" + uuid4().hex
    async with db.bind.begin() as conn:
        source = await conn.scalar(text("SELECT current_schema()"))
        await _create_legacy_schema(conn, source, schema)
        try:
            command = credit_fixture
            tid, result_id = uuid4(), uuid4()
            is_committed = corruption == "ledger_amount"
            if corruption in {"ledger_amount", "settlement_key"}:
                await conn.execute(
                    text(
                        "INSERT INTO "
                        "credit_transactions(id,user_id,amount,reason,"
                        "reference_id,idempotency_key) "
                        "VALUES (:tid,:uid,-9,'chat_usage',:rid,:key)"
                    ),
                    {
                        "tid": tid,
                        "uid": command.user_id,
                        "rid": result_id,
                        "key": f"billing:credit-settlement:{command.user_id}:"
                        f"{command.request_key}",
                    },
                )
            await conn.execute(
                text(
                    "INSERT INTO "
                    "credit_reservations(user_id,request_key,quote_id,status,"
                    "reserved_credit,result_id,transaction_id,"
                    "created_at,finalized_at) "
                    "VALUES (:uid,:key,:qid,:status,10,:rid,:tid,:now,:final)"
                ),
                {
                    "uid": command.user_id,
                    "key": uuid4()
                    if corruption == "quote_identity"
                    else command.request_key,
                    "qid": command.quote_id,
                    "status": "committed" if is_committed else "reserved",
                    "rid": result_id if is_committed else None,
                    "tid": tid if is_committed else None,
                    "now": NOW,
                    "final": NOW if is_committed else None,
                },
            )
            before = {table: await _rows(conn, table) for table in TABLES[:-1]}
            with pytest.raises(DBAPIError):
                async with conn.begin_nested():
                    await conn.run_sync(_migrate, "upgrade")
            for table, rows in before.items():
                assert await _rows(conn, table) == rows
            assert not await conn.run_sync(
                lambda c: inspect(c).has_table("billing_credit_bindings", schema=schema)
            )
        finally:
            # Failed outer transactions roll back CREATE SCHEMA as well.
            if sys.exc_info()[0] is None:
                await conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))
