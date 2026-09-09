from alembic import op

revision = "0014"
down_revision = "0013"


def upgrade():
    op.execute(
        "\nCREATE TABLE product_daily_stats (\n\tproduct_id UUID NOT NULL, \n\tday DATE NOT NULL, \n\tactive_users BIGINT DEFAULT '0' NOT NULL, \n\tsucceeded BIGINT DEFAULT '0' NOT NULL, \n\tfailed BIGINT DEFAULT '0' NOT NULL, \n\tcancelled BIGINT DEFAULT '0' NOT NULL, \n\tstale BIGINT DEFAULT '0' NOT NULL, \n\tmessages BIGINT DEFAULT '0' NOT NULL, \n\tconversations BIGINT DEFAULT '0' NOT NULL, \n\ttransitions BIGINT DEFAULT '0' NOT NULL, \n\tinput_tokens BIGINT DEFAULT '0' NOT NULL, \n\toutput_tokens BIGINT DEFAULT '0' NOT NULL, \n\tcost_credit BIGINT DEFAULT '0' NOT NULL, \n\trevenue JSONB DEFAULT '{}'::jsonb NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (product_id, day), \n\tFOREIGN KEY(product_id) REFERENCES products (id)\n)\n\n"
    )
    op.execute(
        "\nCREATE TABLE product_version_daily_stats (\n\tproduct_id UUID NOT NULL, \n\tproduct_snapshot_id UUID NOT NULL, \n\tday DATE NOT NULL, \n\tactive_users BIGINT DEFAULT '0' NOT NULL, \n\tsucceeded BIGINT DEFAULT '0' NOT NULL, \n\tfailed BIGINT DEFAULT '0' NOT NULL, \n\tcancelled BIGINT DEFAULT '0' NOT NULL, \n\tstale BIGINT DEFAULT '0' NOT NULL, \n\tmessages BIGINT DEFAULT '0' NOT NULL, \n\tconversations BIGINT DEFAULT '0' NOT NULL, \n\ttransitions BIGINT DEFAULT '0' NOT NULL, \n\tinput_tokens BIGINT DEFAULT '0' NOT NULL, \n\toutput_tokens BIGINT DEFAULT '0' NOT NULL, \n\tcost_credit BIGINT DEFAULT '0' NOT NULL, \n\trevenue JSONB DEFAULT '{}'::jsonb NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (product_snapshot_id, day), \n\tFOREIGN KEY(product_id, product_snapshot_id) REFERENCES product_snapshots (product_id, id)\n)\n\n"
    )
    op.execute(
        "CREATE INDEX ix_product_version_daily_stats_product_id ON product_version_daily_stats (product_id)"
    )
    op.execute(
        "\nCREATE TABLE product_user_daily_activity (\n\tproduct_id UUID NOT NULL, \n\tday DATE NOT NULL, \n\tuser_id UUID NOT NULL, \n\tPRIMARY KEY (product_id, day, user_id), \n\tFOREIGN KEY(product_id) REFERENCES products (id), \n\tFOREIGN KEY(user_id) REFERENCES users (id)\n)\n\n"
    )
    op.execute(
        "\nCREATE TABLE product_version_user_daily_activity (\n\tproduct_id UUID NOT NULL, \n\tproduct_snapshot_id UUID NOT NULL, \n\tday DATE NOT NULL, \n\tuser_id UUID NOT NULL, \n\tPRIMARY KEY (product_snapshot_id, day, user_id), \n\tFOREIGN KEY(product_id, product_snapshot_id) REFERENCES product_snapshots (product_id, id), \n\tFOREIGN KEY(user_id) REFERENCES users (id)\n)\n\n"
    )
    op.execute(
        "CREATE INDEX ix_product_version_user_daily_activity_product_id ON product_version_user_daily_activity (product_id)"
    )
    op.execute(
        "\nCREATE TABLE product_stats_dirty_days (\n\tproduct_id UUID NOT NULL, \n\tday DATE NOT NULL, \n\trequested_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (product_id, day), \n\tFOREIGN KEY(product_id) REFERENCES products (id)\n)\n\n"
    )
    op.execute(
        "INSERT INTO product_stats_dirty_days(product_id,day)\nSELECT product_id,(finished_at AT TIME ZONE 'Asia/Seoul')::date FROM product_generations WHERE finished_at IS NOT NULL\nUNION SELECT product_id,(attributed_at AT TIME ZONE 'Asia/Seoul')::date FROM product_payment_events\nUNION SELECT product_id,(created_at AT TIME ZONE 'Asia/Seoul')::date FROM conversations WHERE initial_snapshot_id IS NOT NULL\nUNION SELECT c.product_id,(v.created_at AT TIME ZONE 'Asia/Seoul')::date FROM conversation_version_changes v JOIN conversations c ON c.id=v.conversation_id\nON CONFLICT DO NOTHING"
    )


def downgrade():
    raise RuntimeError("Use a reviewed forward migration.")
