"""Durable bounded recovery and manual attempt audit; preserve generation facts."""

from pathlib import Path

from alembic import op

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        (Path(__file__).parents[1] / "sql/0036_answer_recovery_policy.sql").read_text(
            encoding="utf-8"
        )
    )


def downgrade() -> None:
    # Recovery history must never be discarded and silently replenish retry budgets.
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM answer_recovery_attempts)
                OR EXISTS (SELECT 1 FROM product_generations WHERE
                    answer_recovery_attempts > 0 OR answer_recovery_next_at IS NOT NULL
                    OR answer_recovery_quarantined_at IS NOT NULL) THEN
                RAISE EXCEPTION 'Preserve answer recovery history; downgrade refused';
            END IF;
        END $$;
    """)
    op.drop_table("answer_recovery_attempts")
    op.drop_constraint(
        "ck_answer_recovery_attempts", "product_generations", type_="check"
    )
    op.drop_column("product_generations", "answer_recovery_quarantined_at")
    op.drop_column("product_generations", "answer_recovery_next_at")
    op.drop_column("product_generations", "answer_recovery_attempts")
