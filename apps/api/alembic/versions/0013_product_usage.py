from alembic import op

revision = "0013"
down_revision = "0012a"


def upgrade():
    op.execute(
        "\nCREATE TABLE product_generations (\n\tuser_id UUID NOT NULL, \n\tconversation_id UUID NOT NULL, \n\tproduct_id UUID NOT NULL, \n\tproduct_snapshot_id UUID NOT NULL, \n\tmodel_id UUID NOT NULL, \n\tmodel_name TEXT NOT NULL, \n\treasoning_effort TEXT NOT NULL, \n\trequest_key TEXT NOT NULL, \n\tinput_digest TEXT NOT NULL, \n\tresult_digest TEXT, \n\tstatus TEXT DEFAULT 'pending' NOT NULL, \n\tmessage_count INTEGER DEFAULT '0' NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tfinished_at TIMESTAMP WITH TIME ZONE, \n\tid UUID DEFAULT gen_random_uuid() NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_generation_request UNIQUE (user_id, request_key), \n\tCONSTRAINT uq_generation_version UNIQUE (id, product_snapshot_id), \n\tFOREIGN KEY(product_id, product_snapshot_id) REFERENCES product_snapshots (product_id, id), \n\tCONSTRAINT ck_generation_status CHECK (status IN ('pending','succeeded','failed','cancelled','stale')), \n\tCONSTRAINT ck_generation_messages CHECK (message_count >= 0), \n\tFOREIGN KEY(user_id) REFERENCES users (id), \n\tFOREIGN KEY(conversation_id) REFERENCES conversations (id), \n\tFOREIGN KEY(product_id) REFERENCES products (id), \n\tFOREIGN KEY(model_id) REFERENCES models (id)\n)\n\n"
    )
    op.execute(
        "CREATE INDEX ix_generation_product_finished ON product_generations (product_id, finished_at)"
    )
    op.execute(
        "\nCREATE TABLE product_payment_events (\n\tpayment_id UUID NOT NULL, \n\tsale_id UUID, \n\tproduct_id UUID NOT NULL, \n\tproduct_snapshot_id UUID NOT NULL, \n\tevent_key TEXT NOT NULL, \n\tkind TEXT NOT NULL, \n\tamount NUMERIC(20, 2) NOT NULL, \n\tcurrency TEXT NOT NULL, \n\toccurred_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tattributed_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID DEFAULT gen_random_uuid() NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_product_payment_event_key UNIQUE (event_key), \n\tFOREIGN KEY(product_id, product_snapshot_id) REFERENCES product_snapshots (product_id, id), \n\tCONSTRAINT ck_product_payment_kind CHECK (kind IN ('sale','refund')), \n\tCONSTRAINT ck_product_payment_parent CHECK ((kind='sale' AND sale_id IS NULL) OR (kind='refund' AND sale_id IS NOT NULL)), \n\tCONSTRAINT ck_product_payment_amount CHECK (amount > 0), \n\tFOREIGN KEY(payment_id) REFERENCES payments (id), \n\tFOREIGN KEY(sale_id) REFERENCES product_payment_events (id), \n\tFOREIGN KEY(product_id) REFERENCES products (id)\n)\n\n"
    )
    op.execute(
        "CREATE INDEX ix_product_payment_period ON product_payment_events (product_id, attributed_at)"
    )
    op.execute(
        "ALTER TABLE usage_logs ADD COLUMN generation_id UUID, ADD COLUMN product_id UUID, ADD COLUMN product_snapshot_id UUID, ADD COLUMN reasoning_effort TEXT"
    )
    op.execute(
        "ALTER TABLE usage_logs ADD CONSTRAINT uq_usage_generation UNIQUE (generation_id), ADD FOREIGN KEY (generation_id,product_snapshot_id) REFERENCES product_generations(id,product_snapshot_id), ADD FOREIGN KEY (product_id,product_snapshot_id) REFERENCES product_snapshots(product_id,id)"
    )
    op.execute(
        "ALTER TABLE usage_logs ADD CONSTRAINT ck_usage_nonnegative CHECK (input_tokens >= 0 AND output_tokens >= 0 AND cost_credit >= 0) NOT VALID"
    )
    op.execute(
        "ALTER TABLE messages ADD COLUMN generation_id UUID, ADD FOREIGN KEY (generation_id,product_snapshot_id) REFERENCES product_generations(id,product_snapshot_id)"
    )


def downgrade():
    raise RuntimeError(
        "Usage and payment facts must be preserved; use a forward migration."
    )
