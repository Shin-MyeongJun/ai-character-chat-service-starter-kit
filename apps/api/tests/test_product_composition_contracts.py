"""Composition identity/primary transitions and service authorization boundaries."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Column, Index, MetaData, Table, Uuid, text
from sqlalchemy.ext.asyncio import AsyncSession
from test_product_core_contracts import database as core_database_fixture

from app.db.models.product import (
    Product,
    ProductCharacter,
    ProductLorebook,
    ProductLorebookCharacter,
    ProductStartSet,
)
from app.modules.content.lorebook import types as LorebookTypes
from app.modules.content.product import types
from app.modules.content.product.mapper import persistence
from app.modules.content.product.repository import composition as Repository
from app.modules.content.product.service.command import composition, settings

core_database = core_database_fixture


@pytest.fixture
def composition_database(core_database):
    sync_session, session = core_database
    metadata = MetaData()
    for model in (
        ProductCharacter,
        ProductLorebook,
        ProductLorebookCharacter,
        ProductStartSet,
    ):
        columns = []
        for column in model.__table__.columns:
            columns.append(
                Column(
                    column.name,
                    Uuid(native_uuid=False)
                    if isinstance(column.type, Uuid)
                    else column.type,
                    primary_key=column.primary_key,
                    server_default=text("(lower(hex(randomblob(16))))")
                    if column.name == "id"
                    else None,
                )
            )
        Table(model.__tablename__, metadata, *columns)
    characters = metadata.tables[ProductCharacter.__tablename__]
    Index(
        "test_one_primary",
        characters.c.product_id,
        unique=True,
        sqlite_where=characters.c.is_primary.is_(True),
    )
    metadata.create_all(sync_session.get_bind())
    session.delete.side_effect = sync_session.delete
    session.get.side_effect = sync_session.get
    yield sync_session, session


def start_entry(entry_id, lorebook_id):
    now = datetime.now(UTC)
    return LorebookTypes.LorebookEntryInfo(
        id=entry_id,
        lorebook_id=lorebook_id,
        title=None,
        content="Opening",
        entry_type="start_set",
        activation_type="always",
        key_triggers=None,
        match_mode="contains",
        priority=0,
        token_budget=None,
        placement="before_history",
        is_enabled=True,
        metadata={},
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_replacement_reuses_links_switches_primary_and_rebuilds_targets(
    composition_database,
):
    sync_session, session = composition_database
    product_id = uuid4()
    primary = ProductCharacter(
        id=UUID(int=2),
        product_id=product_id,
        character_id=uuid4(),
        is_primary=True,
        role_order=0,
    )
    secondary = ProductCharacter(
        id=UUID(int=1),
        product_id=product_id,
        character_id=uuid4(),
        is_primary=False,
        role_order=1,
    )
    removed = ProductCharacter(
        id=uuid4(),
        product_id=product_id,
        character_id=uuid4(),
        is_primary=False,
        role_order=2,
    )
    book = ProductLorebook(
        id=uuid4(),
        product_id=product_id,
        lorebook_id=uuid4(),
        role="detail",
        scope="selected",
        priority=0,
        is_required=True,
    )
    removed_book = ProductLorebook(
        id=uuid4(),
        product_id=product_id,
        lorebook_id=uuid4(),
        role="detail",
        scope="all",
        priority=0,
        is_required=True,
    )
    sync_session.add_all([primary, secondary, removed, book, removed_book])
    sync_session.add(
        ProductLorebookCharacter(
            product_id=product_id,
            product_character_id=primary.id,
            product_lorebook_id=book.id,
        )
    )
    sync_session.flush()
    new_character_id = uuid4()
    value = types.ProductCompositionInfo(
        characters=(
            types.CharacterSelection(secondary.character_id, True),
            types.CharacterSelection(primary.character_id),
            types.CharacterSelection(new_character_id),
        ),
        lorebooks=(
            types.LorebookSelection(
                book.lorebook_id,
                "selected",
                (secondary.character_id, new_character_id),
                "main",
                9,
                False,
            ),
        ),
    )
    await Repository.replace_product_composition(session, product_id, value)
    row = await Repository.get_product_composition(session, product_id)
    characters_by_source_id = {entity.character_id: entity for entity in row.characters}
    assert characters_by_source_id[primary.character_id].id == primary.id
    assert characters_by_source_id[secondary.character_id].id == secondary.id
    assert removed.character_id not in characters_by_source_id
    assert [entity.character_id for entity in row.characters] == [
        secondary.character_id,
        primary.character_id,
        new_character_id,
    ]
    assert [entity.character_id for entity in row.characters if entity.is_primary] == [
        secondary.character_id
    ]
    assert len(row.books) == 1 and row.books[0].id == book.id
    assert row.books[0].priority == 9 and not row.books[0].is_required
    assert {entity.product_character_id for entity in row.links} == {
        secondary.id,
        characters_by_source_id[new_character_id].id,
    }
    info = persistence.product_composition_row_to_info(row)
    assert info.characters == value.characters
    assert set(info.lorebooks[0].character_ids) == {
        secondary.character_id,
        new_character_id,
    }


@pytest.mark.asyncio
async def test_settings_keep_policy_json_and_requested_start_order(
    composition_database,
):
    sync_session, session = composition_database
    product = Product(
        id=uuid4(),
        owner_id=uuid4(),
        title="Draft",
        status="draft",
        visibility="private",
        replacement_policy={},
    )
    sync_session.add(product)
    old_id, first_id, second_id, book_id = uuid4(), uuid4(), uuid4(), uuid4()
    sync_session.add(
        ProductStartSet(
            id=uuid4(),
            product_id=product.id,
            lorebook_id=book_id,
            entry_id=old_id,
            sort_order=0,
        )
    )
    sync_session.flush()
    replacement_id = uuid4()
    value = types.ProductSettingsInfo(
        uuid4(),
        "high",
        (second_id, first_id),
        replacement_scope="allowlist",
        replacement_model_ids=(replacement_id,),
        unavailable_policy="pause",
    )
    await Repository.set_product_settings(
        session,
        product.id,
        value,
        [start_entry(first_id, book_id), start_entry(second_id, book_id)],
    )
    links = await Repository.list_product_start_sets(session, product.id)
    assert [
        link.entry_id for link in sorted(links, key=lambda item: item.sort_order)
    ] == [second_id, first_id]
    assert {link.entry_id for link in links} == {first_id, second_id}
    assert (
        product.default_model_id == value.model_id
        and product.reasoning_effort == "high"
    )
    assert product.replacement_policy == {
        "scope": "allowlist",
        "model_ids": [str(replacement_id)],
        "unavailable": "pause",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("failed_stage", [None, "product", "character", "lorebook"])
async def test_composition_checks_owner_and_sources_before_write(
    monkeypatch, failed_stage
):
    trace = []
    owner_id, product_id, character_id, book_id = uuid4(), uuid4(), uuid4(), uuid4()
    value = types.ProductCompositionInfo(
        (types.CharacterSelection(character_id),), (types.LorebookSelection(book_id),)
    )

    def checked(stage):
        async def check(_session, command):
            trace.append(stage)
            assert command.owner_id == owner_id and command.lock is True
            if stage == failed_stage:
                raise LookupError("Not owned")

        return AsyncMock(side_effect=check)

    monkeypatch.setattr(
        composition.QueryService, "get_owned_product", checked("product")
    )
    monkeypatch.setattr(
        composition.CharacterQueryService, "get_owned_characters", checked("character")
    )
    monkeypatch.setattr(
        composition.LorebookQueryService, "get_owned_lorebooks", checked("lorebook")
    )
    write = AsyncMock()
    monkeypatch.setattr(composition.Repository, "replace_product_composition", write)
    async with AsyncSession() as session:
        command = types.ReplaceCompositionCommand(
            product_id=product_id, owner_id=owner_id, value=value
        )
        if failed_stage:
            with pytest.raises(LookupError):
                await composition.replace_composition(session, command)
            write.assert_not_awaited()
            assert (
                trace
                == ["product", "character", "lorebook"][: trace.index(failed_stage) + 1]
            )
        else:
            assert await composition.replace_composition(session, command) == value
            assert trace == ["product", "character", "lorebook"]
            write.assert_awaited_once_with(session, product_id, value)
        assert not session.in_transaction()


@pytest.mark.asyncio
@pytest.mark.parametrize("valid_entries", [True, False])
async def test_settings_only_write_start_entries_returned_in_product_scope(
    monkeypatch, valid_entries
):
    owner_id, product_id, book_id, entry_id = uuid4(), uuid4(), uuid4(), uuid4()
    value = types.ProductSettingsInfo(uuid4(), "medium", (entry_id,))
    monkeypatch.setattr(settings.QueryService, "get_owned_product", AsyncMock())
    validate = AsyncMock()
    monkeypatch.setattr(settings.LlmQueryService, "validate_model", validate)
    monkeypatch.setattr(
        settings.CompositionCommandService,
        "get_composition",
        AsyncMock(
            return_value=types.ProductCompositionInfo(
                lorebooks=(types.LorebookSelection(book_id),)
            )
        ),
    )
    entries = [start_entry(entry_id, book_id)] if valid_entries else []
    lookup = AsyncMock(return_value=entries)
    monkeypatch.setattr(settings.LorebookQueryService, "get_start_entries", lookup)
    write = AsyncMock()
    monkeypatch.setattr(settings.Repository, "set_product_settings", write)
    async with AsyncSession() as session:
        command = types.SetSettingsCommand(
            product_id=product_id, owner_id=owner_id, value=value
        )
        if valid_entries:
            assert await settings.set_settings(session, command) == value
            write.assert_awaited_once_with(session, product_id, value, entries)
        else:
            with pytest.raises(ValueError, match="enabled start_set"):
                await settings.set_settings(session, command)
            write.assert_not_awaited()
        lookup.assert_awaited_once_with(
            session,
            LorebookTypes.GetStartEntriesCommand(
                ids=(entry_id,), lorebook_ids=(book_id,)
            ),
        )
        assert not session.in_transaction()
        assert validate.await_args.args[1].model_id == value.model_id
