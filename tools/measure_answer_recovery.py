"""Measure the repository's recovery SELECT in an isolated local audit schema.

Run with the project's Python. Only the dedicated localhost audit test DB is
accepted. Synthetic generations use the ORM column layout, constraints and
indexes, omitting foreign keys because no parent/domain data is needed here.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from dotenv import dotenv_values
from sqlalchemy import Connection, ExecutionContext, event, literal, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.schema import CreateIndex, CreateTable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/api"))

from app.db.models.product_usage import ProductGeneration  # noqa: E402
from app.modules.chatting.chat import repository as Repository  # noqa: E402

NOW = datetime(2026, 11, 2, tzinfo=UTC)
OLD_INDEX = "ix_product_generations_answer_lease_until"
NEW_INDEX = "ix_generation_pending_answer_lease"


async def measure(rows: int, repeats: int, output: Path) -> None:
    settings = dotenv_values(ROOT / ".env.audit-test.local", interpolate=False)
    url = settings.get("TEST_DATABASE_URL") or ""
    parsed = urlsplit(url)
    if not (
        parsed.scheme == "postgresql+asyncpg"
        and parsed.hostname in {"localhost", "127.0.0.1"}
        and parsed.path.removeprefix("/").startswith("chatkit_audit_test_")
        and (parsed.username or "").startswith("chatkit_test_")
        and parsed.password
        and not parsed.query
        and not parsed.fragment
    ):
        raise SystemExit("A dedicated local .env.audit-test.local DB is required.")
    schema = "u17_measure_" + uuid4().hex
    engine = create_async_engine(url, connect_args={"timeout": 5})
    report: dict[str, object] = {"rows": rows, "repeats": repeats, "results": []}
    results: list[dict[str, object]] = []
    report["results"] = results
    try:
        async with engine.connect() as connection:
            report["postgresql"] = await connection.scalar(text("SELECT version()"))
            await connection.execute(text(f"CREATE SCHEMA {schema}"))
            await connection.execute(text(f"SET search_path TO {schema}, public"))
            table = ProductGeneration.__table__
            await connection.execute(
                CreateTable(table, include_foreign_key_constraints=[])
            )
            for index in table.indexes:
                if index.name not in {OLD_INDEX, NEW_INDEX}:
                    await connection.execute(CreateIndex(index))
            await connection.commit()
            # Capture SQL and typed binds from the actual repository execution.
            captured: list[tuple[str, tuple[object, ...]]] = []

            def capture(
                conn: Connection,
                cursor: object,
                statement: str,
                parameters: tuple[object, ...],
                context: ExecutionContext,
                executemany: bool,
            ) -> None:
                captured.append((statement, tuple(parameters)))

            event.listen(connection.sync_connection, "before_cursor_execute", capture)
            try:
                async with AsyncSession(bind=connection) as session:
                    await Repository.list_expired_answers(session, NOW, 100)
            finally:
                event.remove(
                    connection.sync_connection, "before_cursor_execute", capture
                )
            sql, parameters = captured[0]
            report["sql"] = sql
            arguments = ", ".join(
                str(
                    literal(value).compile(
                        dialect=postgresql.dialect(),
                        compile_kwargs={"literal_binds": True},
                    )
                )
                for value in parameters
            )
            driver = (await connection.get_raw_connection()).driver_connection
            for distribution in (
                "terminal_tail",
                "terminal_spread",
                "backlog",
                "no_due",
            ):
                await connection.execute(text("TRUNCATE product_generations"))
                pending = {
                    "terminal_tail": "i > :rows - 1000",
                    "terminal_spread": "i % 100 = 0",
                    "backlog": "i % 2 = 0",
                    "no_due": "i > :rows - 1000",
                }[distribution]
                due = "FALSE" if distribution == "no_due" else "i % 2 = 0"
                # Terminal leases precede live/due pending leases in the tail
                # case; spread/backlog exercise different candidate densities.
                await connection.execute(
                    text(f"""
                    INSERT INTO product_generations (
                        id, user_id, conversation_id, product_id, product_snapshot_id,
                        model_id, model_name, reasoning_effort, request_key,
                        input_digest, status, created_at, finished_at,
                        answer_lease_until, answer_metadata
                    )
                    SELECT md5(i::text)::uuid,
                        md5('user')::uuid, md5('conversation')::uuid,
                        md5('product')::uuid, md5('snapshot')::uuid, md5('model')::uuid,
                        'test-model', 'none', i::text, repeat('a', 64),
                        CASE WHEN {pending} THEN 'pending' ELSE 'succeeded' END,
                        CAST(:now AS timestamptz) - interval '2 days',
                        CASE WHEN {pending} THEN NULL ELSE CAST(:now AS timestamptz) - interval '1 day' END,
                        CASE WHEN ({pending}) AND NOT ({due})
                             THEN CAST(:now AS timestamptz) + interval '1 hour'
                             ELSE CAST(:now AS timestamptz) - interval '2 days' + i * interval '0.1 second' END,
                        jsonb_build_object('phase', 'result_ready',
                            'content', repeat(md5(i::text), 32))
                    FROM generate_series(1, :rows) i
                """),
                    {"rows": rows, "now": NOW},
                )
                await connection.commit()
                for variant in ("full", "partial", "partial_cleared"):
                    await connection.execute(text(f"DROP INDEX IF EXISTS {OLD_INDEX}"))
                    await connection.execute(text(f"DROP INDEX IF EXISTS {NEW_INDEX}"))
                    if variant == "full":
                        index_name = OLD_INDEX
                        predicate = ""
                    else:
                        index_name = NEW_INDEX
                        predicate = "WHERE status = 'pending' AND answer_lease_until IS NOT NULL"
                    if variant == "partial_cleared":
                        await connection.execute(
                            text("""
                            UPDATE product_generations SET answer_lease_until = NULL
                            WHERE status <> 'pending'
                        """)
                        )
                    await connection.execute(
                        text(
                            f"CREATE INDEX {index_name} ON product_generations(answer_lease_until) {predicate}"
                        )
                    )
                    await connection.commit()
                    # VACUUM requires autocommit and keeps dead row/index entries
                    # from distorting the steady-state comparison.
                    await driver.execute("VACUUM (ANALYZE) product_generations")
                    size = await connection.scalar(
                        text("SELECT pg_relation_size(CAST(:name AS regclass))"),
                        {"name": index_name},
                    )
                    counts = (
                        (
                            await connection.execute(
                                text("""
                        SELECT count(*) FILTER (WHERE status = 'pending') AS pending,
                               count(*) FILTER (WHERE status = 'pending'
                                   AND answer_lease_until <= :now) AS due
                        FROM product_generations
                    """),
                                {"now": NOW},
                            )
                        )
                        .mappings()
                        .one()
                    )
                    await connection.commit()
                    for mode in ("force_custom_plan", "force_generic_plan"):
                        await driver.execute(f"SET plan_cache_mode = {mode}")
                        await driver.execute(f"PREPARE u17_recovery AS {sql}")
                        plans = []
                        try:
                            # One warm-up, then repeated server-side timings.
                            for _ in range(repeats + 1):
                                raw = await driver.fetchval(
                                    "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) "
                                    f"EXECUTE u17_recovery({arguments})"
                                )
                                plans.append(
                                    (json.loads(raw) if isinstance(raw, str) else raw)[
                                        0
                                    ]
                                )
                        finally:
                            await driver.execute("DEALLOCATE u17_recovery")
                        entry = {
                            "distribution": distribution,
                            "variant": variant,
                            "plan_mode": mode,
                            "index_bytes": size,
                            "counts": dict(counts),
                            "median_execution_ms": statistics.median(
                                p["Execution Time"] for p in plans[1:]
                            ),
                            "runs": plans[1:],
                        }
                        results.append(entry)
                        print(
                            f"{distribution} {variant} {mode}: "
                            f"{entry['median_execution_ms']:.3f}ms, index={size}",
                            flush=True,
                        )
            await connection.execute(text(f"DROP SCHEMA {schema} CASCADE"))
            await connection.commit()
    finally:
        # A separate connection also cleans up after a failed measurement.
        async with engine.begin() as cleanup:
            await cleanup.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        await engine.dispose()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=100000)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 10000 <= args.rows <= 1000000 or not 1 <= args.repeats <= 20:
        parser.error("rows must be 10,000–1,000,000 and repeats 1–20")
    asyncio.run(measure(args.rows, args.repeats, args.output))


if __name__ == "__main__":
    main()
