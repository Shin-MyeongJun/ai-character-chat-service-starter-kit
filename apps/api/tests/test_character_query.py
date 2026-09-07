from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from app.db.models.character import Character, CharacterAsset, CharacterImage
from app.modules.character import repository, types
from app.modules.character.service import query
from sqlalchemy import create_engine, event
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateTable

pytestmark = pytest.mark.asyncio


def uid(value):
    # SQLite treats the PostgreSQL UUID column as numeric when all digits match.
    return UUID(int=(0xA << 124) + value)


def make_character(value, owner_id, created_at):
    return Character(
        id=uid(value),
        owner_id=owner_id,
        name=f"Character {value}",
        description=f"Description {value}",
        persona_prompt=f"Private persona {value}",
        visibility="private" if value == 10 else "public",
        status="draft" if value == 10 else "approved",
        default_model_id=uid(900),
        created_at=created_at,
        updated_at=created_at,
    )


class AsyncScalarsAdapter:
    """Run repository SELECTs on SQLite without requiring an async DB driver."""

    def __init__(self, session):
        self.sync_session = session

    async def scalars(self, statement):
        return self.sync_session.scalars(statement)


@pytest.fixture
def data():
    older = datetime(2026, 9, 1, tzinfo=UTC)
    newer = older + timedelta(days=1)
    owner_id = uid(800)
    other_owner_id = uid(801)
    characters = [
        make_character(10, owner_id, older),
        make_character(20, other_owner_id, newer),
        make_character(30, owner_id, newer),
        make_character(40, owner_id, newer),
        make_character(50, other_owner_id, older - timedelta(days=1)),
    ]
    images = [
        CharacterImage(
            id=uid(value),
            character_id=uid(character_id),
            emotion_tag=emotion,
            image_url=f"{value}.png",
            is_default=is_default,
            created_at=created_at,
            updated_at=created_at,
        )
        for value, character_id, emotion, is_default, created_at in [
            (101, 10, "neutral", True, older),
            (102, 10, "happy", False, newer),
            (201, 20, "happy", True, newer),
        ]
    ]
    assets = [
        CharacterAsset(
            id=uid(value),
            character_id=uid(character_id),
            asset_type=asset_type,
            purpose="promotion",
            file_url=f"{value}.{asset_type}",
            created_at=created_at,
            updated_at=created_at,
        )
        for value, character_id, asset_type, created_at in [
            (301, 10, "audio", older),
            (302, 10, "image", newer),
            (401, 20, "audio", newer),
        ]
    ]
    return SimpleNamespace(
        characters=characters,
        images=images,
        assets=assets,
        owner_id=owner_id,
        other_owner_id=other_owner_id,
    )


@pytest.fixture
def database(data):
    engine = create_engine("sqlite://")
    # Exercise actual SELECT predicates. PostgreSQL-only indexes are not created;
    # UUIDs and timestamps are supplied explicitly instead of using DB defaults.
    with engine.begin() as connection:
        for model in (Character, CharacterImage, CharacterAsset):
            connection.execute(CreateTable(model.__table__))
    with Session(engine, expire_on_commit=False) as session:
        session.add_all(data.characters + data.images + data.assets)
        session.commit()
        yield AsyncScalarsAdapter(session)
    engine.dispose()


async def test_all_character_pages_include_private_characters_and_handle_timestamp_ties(
    database,
):
    seen = []
    cursor = None
    while True:
        page = await query.list_characters(database, cursor=cursor, limit=2)
        assert isinstance(page, types.CharacterPage)
        assert all(isinstance(item, types.CharacterInfo) for item in page.items)
        seen.extend(item.id for item in page.items)
        cursor = page.next_cursor
        if cursor is None:
            break
        assert cursor.id == page.items[-1].id
        assert cursor.created_at == page.items[-1].created_at
        assert len(seen) <= 5, "The cursor must advance without repeating rows"

    assert seen == [uid(value) for value in (40, 30, 20, 10, 50)]


async def test_owner_filter_is_preserved_across_cursor_pages(database, data):
    first = await query.list_characters_by_owner_id(
        database, owner_id=data.owner_id, limit=2
    )
    second = await query.list_characters_by_owner_id(
        database, owner_id=data.owner_id, cursor=first.next_cursor, limit=2
    )

    assert [item.id for item in first.items] == [uid(40), uid(30)]
    assert [item.id for item in second.items] == [uid(10)]
    assert all(item.owner_id == data.owner_id for item in first.items + second.items)
    assert second.next_cursor is None


async def test_empty_owner_page_and_minimum_limit(database):
    missing = await query.list_characters_by_owner_id(database, owner_id=uid(999))
    assert missing.items == []
    assert missing.next_cursor is None

    first = await query.list_characters(database, limit=0)
    assert [item.id for item in first.items] == [uid(40)]
    assert first.next_cursor.id == uid(40)


async def test_character_detail_and_owner_detail_return_results(database, data):
    result = await query.get_character_by_id(database, character_id=uid(10))
    owned = await query.get_character_by_id_and_owner_id(
        database, character_id=uid(10), owner_id=data.owner_id
    )
    foreign = await query.get_character_by_id_and_owner_id(
        database, character_id=uid(10), owner_id=data.other_owner_id
    )

    assert isinstance(result, types.CharacterInfo)
    assert result == owned
    assert result.persona_prompt == "Private persona 10"
    assert foreign is None
    assert await query.get_character_by_id(database, character_id=uid(999)) is None


@pytest.mark.parametrize(
    ("kind", "own_id", "foreign_id", "result_type"),
    [
        ("image", 101, 201, types.CharacterImageInfo),
        ("asset", 301, 401, types.CharacterAssetInfo),
    ],
)
async def test_individual_media_must_belong_to_requested_character(
    database, kind, own_id, foreign_id, result_type
):
    lookup = getattr(query, f"get_character_{kind}")
    own = await lookup(database, character_id=uid(10), **{f"{kind}_id": uid(own_id)})
    foreign = await lookup(
        database, character_id=uid(10), **{f"{kind}_id": uid(foreign_id)}
    )
    missing = await lookup(database, character_id=uid(10), **{f"{kind}_id": uid(999)})

    assert isinstance(own, result_type)
    assert own.id == uid(own_id)
    assert foreign is None
    assert missing is None


async def test_emotion_match_is_exact_and_has_no_implicit_default_fallback(database):
    happy = await query.get_character_image_by_emotion_tag(
        database, character_id=uid(10), emotion_tag="happy"
    )
    assert isinstance(happy, types.CharacterImageInfo)
    assert happy.id == uid(102)
    for emotion in ("Happy", " happy ", "sad"):
        assert (
            await query.get_character_image_by_emotion_tag(
                database, character_id=uid(10), emotion_tag=emotion
            )
            is None
        )

    default = await query.get_default_character_image(database, character_id=uid(10))
    assert default.id == uid(101)
    assert default.is_default
    assert (
        await query.get_default_character_image(database, character_id=uid(30)) is None
    )


async def test_media_lists_are_scoped_and_asset_type_filters_apply(database):
    images = await query.list_character_images(database, character_id=uid(10))
    assets = await query.list_character_assets(database, character_id=uid(10))
    audio = await query.list_character_assets(
        database, character_id=uid(10), asset_type="audio"
    )

    assert [image.id for image in images] == [uid(101), uid(102)]
    assert all(isinstance(image, types.CharacterImageInfo) for image in images)
    assert [asset.id for asset in assets] == [uid(302), uid(301)]
    assert all(isinstance(asset, types.CharacterAssetInfo) for asset in assets)
    assert [asset.id for asset in audio] == [uid(301)]
    assert (
        await query.list_character_assets(
            database, character_id=uid(10), asset_type="video"
        )
        == []
    )


@pytest.mark.parametrize("character_id", [uid(30), uid(999)])
async def test_empty_and_missing_characters_have_empty_media_lists(
    database, character_id
):
    assert await query.list_character_images(database, character_id=character_id) == []
    assert await query.list_character_assets(database, character_id=character_id) == []


async def test_prompt_returns_only_runtime_prompt_fields(database):
    result = await query.get_character_prompt(database, character_id=uid(10))

    assert isinstance(result, types.CharacterPromptInfo)
    assert asdict(result) == {
        "character_id": uid(10),
        "persona_prompt": "Private persona 10",
        "default_model_id": uid(900),
    }
    assert await query.get_character_prompt(database, character_id=uid(999)) is None


async def test_promotion_contains_scoped_media_and_excludes_prompt(database):
    result = await query.get_character_promotion(database, character_id=uid(10))

    assert isinstance(result, types.CharacterPromotionInfo)
    assert result.character_id == uid(10)
    assert result.name == "Character 10"
    assert result.description == "Description 10"
    assert [image.id for image in result.images] == [uid(101), uid(102)]
    assert [asset.id for asset in result.assets] == [uid(302), uid(301)]
    assert all(isinstance(image, types.CharacterImageInfo) for image in result.images)
    assert all(isinstance(asset, types.CharacterAssetInfo) for asset in result.assets)
    assert "persona_prompt" not in asdict(result)
    assert "default_model_id" not in asdict(result)


async def test_promotion_distinguishes_missing_character_from_empty_media(database):
    empty = await query.get_character_promotion(database, character_id=uid(30))

    assert isinstance(empty, types.CharacterPromotionInfo)
    assert empty.images == []
    assert empty.assets == []
    assert await query.get_character_promotion(database, character_id=uid(999)) is None


async def test_promotion_uses_existing_transaction_without_committing_or_rolling_back(
    monkeypatch, data
):
    monkeypatch.setattr(
        repository, "get_character_by_id", AsyncMock(return_value=data.characters[0])
    )
    monkeypatch.setattr(repository, "list_character_images", AsyncMock(return_value=[]))
    monkeypatch.setattr(repository, "list_character_assets", AsyncMock(return_value=[]))
    async with AsyncSession() as session:
        events = []
        event.listen(
            session.sync_session, "after_commit", lambda _: events.append("commit")
        )
        event.listen(
            session.sync_session, "after_rollback", lambda _: events.append("rollback")
        )
        async with session.begin():
            result = await query.get_character_promotion(session, character_id=uid(10))
            assert result.character_id == uid(10)
            assert session.in_transaction()
            assert events == []
        assert events == ["commit"]


@pytest.mark.parametrize("asset_type", ["unknown", "", "Audio"])
async def test_invalid_asset_type_does_not_query_or_end_callers_transaction(
    monkeypatch, asset_type
):
    all_assets = AsyncMock()
    typed_assets = AsyncMock()
    monkeypatch.setattr(repository, "list_character_assets", all_assets)
    monkeypatch.setattr(repository, "list_character_assets_by_type", typed_assets)
    async with AsyncSession() as session, session.begin():
        with pytest.raises(ValueError):
            await query.list_character_assets(
                session, character_id=uid(10), asset_type=asset_type
            )
        all_assets.assert_not_awaited()
        typed_assets.assert_not_awaited()
        assert session.in_transaction()
