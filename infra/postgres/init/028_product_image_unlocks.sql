CREATE TABLE product_image_unlocks (
    account_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    product_id uuid NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    image_item_id uuid NOT NULL,
    unlocked_at timestamptz NOT NULL DEFAULT statement_timestamp(),
    PRIMARY KEY (account_id, product_id, image_item_id)
);

CREATE INDEX ix_product_image_unlocks_product_id ON product_image_unlocks (product_id);
