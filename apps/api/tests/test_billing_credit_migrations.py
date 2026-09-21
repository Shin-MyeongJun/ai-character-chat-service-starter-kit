"""Credit migration preservation and real online upgrade/downgrade behavior."""

import importlib.util
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError

ROOT = Path(__file__).resolve().parents[3]
MIGRATION = ROOT / "apps/api/alembic/versions/0022_billing_credits.py"


def _run_migration(connection, direction):
    spec = importlib.util.spec_from_file_location("billing_credit_migration", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with Operations.context(MigrationContext.configure(connection)):
        getattr(module, direction)()


def test_credit_upgrade_scope_and_downgrade_guard():
    def render(direction, revisions):
        return subprocess.check_output(
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                "apps/api/alembic.ini",
                direction,
                revisions,
                "--sql",
            ],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
        )

    upgrade = render("upgrade", "0021:0022")
    assert upgrade.count("CREATE TABLE") == 1
    assert "CREATE TABLE credit_reservations" in upgrade
    assert upgrade.count("ALTER TABLE credit_accounts") == 2
    assert "ALTER TABLE credit_transactions" not in upgrade
    assert "UPDATE credit_accounts" not in upgrade
    assert "UPDATE credit_transactions" not in upgrade
    assert "INSERT INTO credit_" not in upgrade
    downgrade = render("downgrade", "0022:0021")
    assert downgrade.index("RAISE EXCEPTION") < downgrade.index("DROP TABLE")
    assert "DROP TABLE credit_transactions" not in downgrade


@pytest.mark.asyncio
async def test_online_credit_migration_preserves_legacy_history_and_guards_downgrade(
    db,
):
    schema = "credit_migration_" + uuid4().hex
    uid, tid, qid = uuid4(), uuid4(), uuid4()
    async with db.bind.begin() as conn:
        reference_schema = await conn.scalar(text("SELECT current_schema()"))
        expected_checks = await conn.run_sync(
            lambda c: inspect(c).get_check_constraints(
                "credit_reservations", schema=reference_schema
            )
        )
        await conn.execute(text(f"CREATE SCHEMA {schema}"))
    try:
        async with db.bind.begin() as conn:
            await conn.execute(text(f"SET LOCAL search_path TO {schema}, public"))
            # Only the legacy tables that 0022 depends on. Preserve their real columns.
            for table in (
                "users",
                "credit_accounts",
                "credit_transactions",
                "billing_quotes",
            ):
                await conn.execute(
                    text(
                        f"CREATE TABLE {table} "
                        f"(LIKE {reference_schema}.{table} INCLUDING ALL)"
                    )
                )
            await conn.execute(
                text("ALTER TABLE credit_accounts DROP COLUMN reserved_credit")
            )
            await conn.execute(
                text("INSERT INTO users(id,email) VALUES (:id,'legacy@credit.test')"),
                {"id": uid},
            )
            await conn.execute(
                text("INSERT INTO credit_accounts(user_id,balance) VALUES (:id,37)"),
                {"id": uid},
            )
            await conn.execute(
                text(
                    "INSERT INTO credit_transactions"
                    "(id,user_id,amount,reason,idempotency_key) "
                    "VALUES (:tid,:uid,37,'purchase','legacy-credit-key')"
                ),
                {"tid": tid, "uid": uid},
            )
            before_account = (
                (
                    await conn.execute(
                        text("SELECT user_id,balance,updated_at FROM credit_accounts")
                    )
                )
                .mappings()
                .one()
            )
            before_ledger = (
                (await conn.execute(text("SELECT * FROM credit_transactions")))
                .mappings()
                .one()
            )
            await conn.run_sync(_run_migration, "upgrade")
            account = dict(
                (await conn.execute(text("SELECT * FROM credit_accounts")))
                .mappings()
                .one()
            )
            assert account.pop("reserved_credit") == 0
            assert account == dict(before_account)
            assert (
                await conn.execute(text("SELECT * FROM credit_transactions"))
            ).mappings().one() == before_ledger
            actual_checks = await conn.run_sync(
                lambda c: inspect(c).get_check_constraints(
                    "credit_reservations", schema=schema
                )
            )
            assert actual_checks == expected_checks
            # Empty reservation history can be downgraded and re-upgraded.
            await conn.run_sync(_run_migration, "downgrade")
            await conn.run_sync(_run_migration, "upgrade")
            await conn.execute(
                text(
                    "INSERT INTO billing_quotes"
                    "(id,user_id,request_key,request_snapshot,"
                    "price_snapshot,created_at,expires_at) "
                    "VALUES (:qid,:uid,:key,'{}','{}',now(),now()+interval '1 minute')"
                ),
                {"qid": qid, "uid": uid, "key": uuid4()},
            )
            # Even released history must be retained for idempotent replays.
            await conn.execute(
                text(
                    "INSERT INTO credit_reservations"
                    "(user_id,request_key,quote_id,status,"
                    "reserved_credit,created_at,finalized_at) "
                    "VALUES (:uid,:key,:qid,'released',10,now(),now())"
                ),
                {"uid": uid, "key": uuid4(), "qid": qid},
            )
            with pytest.raises(DBAPIError, match="Preserve credit reservation history"):
                async with conn.begin_nested():
                    await conn.run_sync(_run_migration, "downgrade")
            assert (
                await conn.scalar(text("SELECT count(*) FROM credit_reservations")) == 1
            )
            assert await conn.scalar(text("SELECT balance FROM credit_accounts")) == 37
    finally:
        async with db.bind.begin() as conn:
            await conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))
