"""Offline migration scope; real DDL parity remains in test_product_migrations."""

import subprocess
import sys
from pathlib import Path

from app.db.models.billing_quote import BillingQuote
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

ROOT = Path(__file__).resolve().parents[3]


def test_quote_upgrade_only_adds_owned_table_and_matches_initial_sql():
    output = subprocess.check_output(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            "apps/api/alembic.ini",
            "upgrade",
            "0020:0021",
            "--sql",
        ],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
    )
    initial = "\n".join(
        line
        for line in (ROOT / "infra/postgres/init/012_billing_quotes.sql")
        .read_text(encoding="utf-8")
        .splitlines()
        if not line.lstrip().startswith("--")
    ).strip()
    assert initial in output
    assert output.count("CREATE TABLE") == 1
    assert "ALTER TABLE" not in output
    assert "DROP TABLE" not in output
    assert "INSERT INTO" not in output  # No made-up operational prices.
    assert "0020 -> 0021" in output
    model_sql = str(
        CreateTable(BillingQuote.__table__).compile(dialect=postgresql.dialect())
    )
    for constraint in (
        "uq_billing_quotes_user_request",
        "ck_billing_quotes_expiration",
        "ck_billing_quotes_snapshots",
    ):
        assert constraint in model_sql and constraint in initial
    assert "ON DELETE RESTRICT" in model_sql and "ON DELETE RESTRICT" in initial
    assert {column.name for column in BillingQuote.__table__.columns} == {
        "id",
        "user_id",
        "request_key",
        "request_snapshot",
        "price_snapshot",
        "created_at",
        "expires_at",
    }


def test_quote_downgrade_refuses_to_discard_saved_quotes():
    output = subprocess.check_output(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            "apps/api/alembic.ini",
            "downgrade",
            "0021:0020",
            "--sql",
        ],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
    )
    assert "IF EXISTS (SELECT 1 FROM billing_quotes)" in output
    assert output.index("RAISE EXCEPTION") < output.index("DROP TABLE billing_quotes")
    assert output.count("DROP TABLE") == 1
