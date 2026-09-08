from alembic import op

revision = "0003"
down_revision = "0002"


def upgrade():
    op.execute(
        "ALTER TABLE lorebook_entries DROP CONSTRAINT ck_lorebook_entries_entry_type"
    )
    op.execute(
        "ALTER TABLE lorebook_entries ADD CONSTRAINT ck_lorebook_entries_entry_type CHECK (entry_type IN ('author_note','world','genre','rule','location','faction','character_relation','event','term','secret','start_set'))"
    )


def downgrade():
    raise RuntimeError("Start sets require a reviewed forward migration.")
