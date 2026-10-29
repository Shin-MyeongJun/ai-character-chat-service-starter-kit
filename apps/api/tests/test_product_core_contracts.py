"""SQLite checks for product scopes and detached values; no PostgreSQL lock races."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import JSON, Column, MetaData, Table, Uuid, create_engine, text, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.db.models.product import Product
from app.db.models.snapshot.product import ProductSnapshot
from app.modules.content.product import types
from app.modules.content.product.mapper import persistence
from app.modules.content.product.repository import core, publication
from app.modules.content.product.repository import tags as TagsRepository


@pytest.fixture
def database():
    metadata = MetaData()
    for model in (Product, ProductSnapshot):
        columns = []
        for column in model.__table__.columns:
            column_type = column.type
            if isinstance(column_type, JSONB):
                column_type = JSON()
            elif isinstance(column_type, Uuid):
                # SQLite's bare UUID type has numeric affinity; hex-only numeric
                # UUIDs must remain text, matching the ORM UUID result processor.
                column_type = Uuid(native_uuid=False)
            default = None
            if column.name in ("created_at", "updated_at"):
                default = text("CURRENT_TIMESTAMP")
            elif column.name == "replacement_policy":
                default = text("'{}'")
            columns.append(
                Column(
                    column.name,
                    column_type,
                    primary_key=column.primary_key,
                    server_default=default,
                )
            )
        Table(model.__tablename__, metadata, *columns)
    engine = create_engine("sqlite://")
    metadata.create_all(engine)
    try:
        with Session(engine) as sync_session:
            session = AsyncMock(spec=AsyncSession)
            session.scalar.side_effect = sync_session.scalar
            session.scalars.side_effect = sync_session.scalars
            session.execute.side_effect = sync_session.execute
            session.add.side_effect = sync_session.add
            session.flush.side_effect = sync_session.flush
            session.refresh.side_effect = sync_session.refresh
            yield sync_session, session
    finally:
        engine.dispose()


def product(owner_id, index, **overrides):
    return Product(
        id=UUID(int=index),
        owner_id=owner_id,
        title="100%_ literal",
        description="Original",
        opening_message="Opening",
        status="draft",
        visibility="private",
        replacement_policy={"models": ["original"]},
        created_at=datetime(2026, 10, 1, tzinfo=UTC),
        updated_at=datetime(2026, 10, 1, tzinfo=UTC),
        **overrides,
    )


@pytest.mark.asyncio
async def test_owner_count_and_page_share_literal_search_and_tie_breaker(database):
    sync_session, session = database
    owner_id = uuid4()
    rows = [product(owner_id, 1), product(owner_id, 2), product(uuid4(), 3)]
    rows.append(
        Product(
            id=UUID(int=4),
            owner_id=owner_id,
            title="100XY wildcard lookalike",
            visibility="private",
            status="draft",
            replacement_policy={},
        )
    )
    sync_session.add_all(rows)
    sync_session.flush()
    assert await core.count_owned(session, owner_id, search="%_") == 2
    page = await core.list_owned(session, owner_id, search="%_", offset=1, limit=1)
    assert [row.id for row in page] == [UUID(int=1)]
    assert await core.count_owned(session, uuid4()) == 0
    assert await core.list_owned(session, uuid4()) == []
    assert await core.get_owned_product(session, rows[0].id, rows[2].owner_id) is None


@pytest.mark.asyncio
async def test_locked_product_lookups_refresh_cached_state_and_keep_missing_none(
    database,
):
    sync_session, session = database
    original = product(uuid4(), 1)
    sync_session.add(original)
    sync_session.flush()
    sync_session.execute(
        update(Product)
        .values(title="Refreshed")
        .execution_options(synchronize_session=False)
    )
    assert original.title != "Refreshed"
    result = await core.get_owned_product(
        session, original.id, original.owner_id, lock=True
    )
    assert result is original and result.title == "Refreshed"
    assert await core.get_product_for_update(session, original.id) is original
    assert await core.get_product(session, original.id, lock=True) is original
    assert await core.get_product(session, uuid4(), lock=True) is None
    assert await publication.get_product_snapshot(session, uuid4(), lock=True) is None


@pytest.mark.asyncio
async def test_tag_parent_read_refreshes_existing_entity_and_keeps_missing_none(
    database,
):
    sync_session, session = database
    entity = product(uuid4(), 1)
    sync_session.add(entity)
    sync_session.flush()
    sync_session.execute(
        update(Product)
        .values(status="approved", visibility="public")
        .execution_options(synchronize_session=False)
    )
    assert entity.status == "draft"
    result = await TagsRepository.get_target_for_tag_access(
        session, entity.id, lock=True
    )
    assert (
        result is entity
        and result.status == "approved"
        and result.visibility == "public"
    )
    assert await TagsRepository.get_target_for_tag_access(session, uuid4()) is None


@pytest.mark.asyncio
async def test_profile_write_and_detached_state_preserve_publication_and_policy(
    database,
):
    sync_session, session = database
    owner_id, product_id = uuid4(), uuid4()
    saved = await core.create_product(
        session, owner_id, types.ProductProfileCommand("Created"), product_id=product_id
    )
    assert saved.id == product_id and saved.status == "draft"
    saved.latest_snapshot_id = uuid4()
    saved.status = "rejected"
    saved.replacement_policy = {"models": ["original"]}
    sync_session.flush()
    result = await core.update_product(
        session,
        product_id,
        owner_id,
        types.ProductProfileCommand("Changed", description=None, opening_message=""),
    )
    assert result is saved
    info = persistence.product_entity_to_info(result)
    state = persistence.product_entity_to_state_info(result)
    assert info is not None and state is not None
    assert (
        info.title == "Changed" and info.status == "rejected" and info.has_publication
    )
    assert info.description is None and info.opening_message == ""
    state.replacement_policy["models"].append("info only")
    assert saved.replacement_policy == {"models": ["original"]}
    assert (
        await core.update_product(
            session, product_id, uuid4(), types.ProductProfileCommand("Denied")
        )
        is None
    )
    assert persistence.product_entity_to_info(None) is None


@pytest.mark.asyncio
async def test_catalog_sql_rows_keep_published_fields_and_cursor_and_snapshot_copy(
    database,
):
    sync_session, session = database
    owner_id = uuid4()
    products = [product(owner_id, 1), product(owner_id, 2), product(owner_id, 3)]
    for index, row in enumerate(products):
        snapshot = ProductSnapshot(
            id=uuid4(),
            product_id=row.id,
            version=1,
            snapshot_schema_version=2,
            snapshot_data={
                "title": f"Published {index}",
                "extension": {"labels": ["original"]},
            },
        )
        row.latest_snapshot_id = snapshot.id
        row.status = "approved"
        row.visibility = "public" if index < 2 else "private"
        sync_session.add_all([row, snapshot])
    sync_session.flush()
    rows = await core.list_catalog(session, limit=1)
    page = persistence.catalog_entities_to_page_info(rows, 1)
    assert len(rows) == 2
    assert [info.title for info in page.items] == ["Published 1"]
    assert page.next_cursor_id == products[1].id
    assert page.items[0].description is None
    next_rows = await core.list_catalog(
        session,
        limit=1,
        cursor_created_at=page.next_cursor_created_at,
        cursor_id=page.next_cursor_id,
    )
    assert (
        persistence.catalog_entities_to_page_info(next_rows, 1).next_cursor_id is None
    )
    snapshot = await publication.get_product_snapshot(session, rows[0][1].id, lock=True)
    info = persistence.product_snapshot_entity_to_info(snapshot)
    assert snapshot is not None and info is not None
    info.snapshot_data["extension"]["labels"].append("info only")
    assert snapshot.snapshot_data["extension"]["labels"] == ["original"]
