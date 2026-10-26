"""Persist exact final chat prompts before provider adapter conversion."""

from pathlib import Path

from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    path = Path(__file__).resolve().parents[1] / "sql/0030_generation_prompts.sql"
    for statement in path.read_text(encoding="utf-8").split(";"):
        if statement.strip():
            op.execute(statement)


def downgrade() -> None:
    op.execute("LOCK TABLE generation_prompts IN ACCESS EXCLUSIVE MODE")
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM generation_prompts) THEN
            RAISE EXCEPTION 'Prompt records exist; preserve them before downgrade';
        END IF;
    END $$;""")
    op.drop_index("ix_generation_conversation_created", "product_generations")
    op.drop_index("ix_generation_created_id", "product_generations")
    op.drop_table("generation_prompts")
