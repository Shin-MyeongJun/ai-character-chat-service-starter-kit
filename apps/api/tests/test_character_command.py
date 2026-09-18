# 저장소 mock과 세션 commit/rollback 이벤트로 소유권·검증·예외 전달을 검사한다. 실제 DB 제약은 별도 통합 테스트 대상이다.
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, call
from uuid import uuid4

import pytest
import pytest_asyncio
from app.db.models.character import Character, CharacterAsset, CharacterImage
from app.modules.content.character import repository, types
from app.modules.content.character.service import command as service
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError, InvalidRequestError
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def session():
    async with AsyncSession() as value:
        yield value


@pytest.fixture
def transaction_events(session):
    events = []
    event.listen(
        session.sync_session, "after_commit", lambda _: events.append("commit")
    )
    event.listen(
        session.sync_session, "after_rollback", lambda _: events.append("rollback")
    )
    return events


@pytest.fixture
def character():
    now = datetime.now(UTC)
    return Character(
        id=uuid4(),
        owner_id=uuid4(),
        name="Original name",
        description="Original description",
        persona_prompt="Original persona",
        visibility="private",
        status="approved",
        default_model_id=uuid4(),
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def commands(character):
    owner = {"character_id": character.id, "owner_id": character.owner_id}
    return SimpleNamespace(
        create=types.CreateCharacterCommand(
            owner_id=character.owner_id, name="New name", persona_prompt="New persona"
        ),
        update=types.UpdateCharacterCommand(
            **owner,
            name="Updated name",
            persona_prompt="Updated persona",
            description=None,
            visibility="public",
        ),
        status=types.ChangeCharacterStatusCommand(**owner, status="rejected"),
        delete=types.DeleteCharacterCommand(**owner),
        default_image=types.SetDefaultCharacterImageCommand(**owner, image_id=uuid4()),
        delete_image=types.DeleteCharacterImageCommand(**owner, image_id=uuid4()),
        delete_asset=types.DeleteCharacterAssetCommand(**owner, asset_id=uuid4()),
        add_image=types.CreateCharacterImageCommand(
            **owner, emotion_tag="happy", image_url="pending.png"
        ),
        add_asset=types.CreateCharacterAssetCommand(
            **owner, asset_type="audio", purpose="voice", file_url="pending.wav"
        ),
    )


@pytest.fixture
def repo(monkeypatch, character):
    mocks = SimpleNamespace()
    names = (
        "create_character",
        "get_character_by_id_and_owner_id",
        "update_character",
        "delete_character",
        "add_character_image",
        "set_default_character_image",
        "get_character_image_by_id_and_character_id",
        "delete_character_image",
        "add_character_asset",
        "get_character_asset_by_id_and_character_id",
        "delete_character_asset",
    )
    for name in names:
        mock = AsyncMock()
        monkeypatch.setattr(repository, name, mock)
        setattr(mocks, name, mock)
    mocks.get_character_by_id_and_owner_id.return_value = character
    mocks.update_character.return_value = character
    return mocks


async def test_create_returns_result_with_db_defaults_after_commit(
    session, transaction_events, commands, repo
):
    async def persist(db_session, entity):
        assert db_session.in_transaction()
        entity.id = uuid4()
        entity.created_at = entity.updated_at = datetime.now(UTC)
        return entity

    repo.create_character.side_effect = persist

    result = await service.create_character(session, commands.create)

    assert isinstance(result, types.CharacterInfo)
    assert result.owner_id == commands.create.owner_id
    assert result.status == "draft"
    assert result.visibility == "private"
    assert result.created_at is not None
    assert transaction_events == ["commit"]
    assert not session.in_transaction()


@pytest.mark.parametrize("operation", ["create", "update"])
@pytest.mark.parametrize(
    ("field", "value"),
    [("name", " \t"), ("persona_prompt", "\n "), ("visibility", "unknown")],
)
async def test_invalid_profile_rolls_back_without_repository_write(
    session, transaction_events, commands, repo, operation, field, value
):
    invalid_command = replace(getattr(commands, operation), **{field: value})
    function = getattr(service, f"{operation}_character")

    with pytest.raises(ValueError):
        await function(session, invalid_command)

    repo.create_character.assert_not_awaited()
    repo.update_character.assert_not_awaited()
    assert transaction_events == ["rollback"]
    assert not session.in_transaction()


async def test_update_preserves_identity_and_status_and_clears_optional_fields(
    session, transaction_events, character, commands, repo
):
    result = await service.update_character(session, commands.update)

    assert result.id == commands.update.character_id
    assert result.owner_id == commands.update.owner_id
    assert result.status == "approved"
    assert result.name == commands.update.name
    assert result.persona_prompt == commands.update.persona_prompt
    assert result.visibility == "public"
    assert result.description is None
    assert result.default_model_id is None
    repo.get_character_by_id_and_owner_id.assert_has_awaits(
        [
            call(session, character.id, character.owner_id, for_update=True),
            call(session, character.id, character.owner_id, for_update=True),
        ]
    )
    assert transaction_events == ["commit"]


@pytest.mark.parametrize(
    ("function_name", "command_name", "mutation"),
    [
        ("update_character", "update", "update_character"),
        ("change_character_status", "status", "update_character"),
        ("delete_character", "delete", "delete_character"),
        ("set_default_character_image", "default_image", "set_default_character_image"),
        ("delete_character_image", "delete_image", "delete_character_image"),
        ("delete_character_asset", "delete_asset", "delete_character_asset"),
    ],
)
async def test_missing_or_non_owned_character_prevents_mutation(
    session, transaction_events, commands, repo, function_name, command_name, mutation
):
    repo.get_character_by_id_and_owner_id.return_value = None
    command = getattr(commands, command_name)

    with pytest.raises(LookupError, match="Character not found"):
        await getattr(service, function_name)(session, command)

    repo.get_character_by_id_and_owner_id.assert_awaited_once_with(
        session, command.character_id, command.owner_id, for_update=True
    )
    getattr(repo, mutation).assert_not_awaited()
    assert transaction_events == ["rollback"]


async def test_status_change_leaves_profile_unchanged(
    session, transaction_events, character, commands, repo
):
    original_name = character.name
    original_visibility = character.visibility

    result = await service.change_character_status(session, commands.status)

    assert result.status == "rejected"
    assert result.name == original_name
    assert result.visibility == original_visibility
    assert transaction_events == ["commit"]


@pytest.mark.parametrize("operation", ["create", "status"])
async def test_invalid_status_is_rejected_before_write(
    session, transaction_events, commands, repo, operation
):
    invalid_command = replace(getattr(commands, operation), status="unknown")
    function = (
        service.create_character
        if operation == "create"
        else service.change_character_status
    )

    with pytest.raises(ValueError):
        await function(session, invalid_command)

    repo.create_character.assert_not_awaited()
    repo.update_character.assert_not_awaited()
    assert transaction_events == ["rollback"]


async def test_delete_commits_after_owner_check(
    session, transaction_events, character, commands, repo
):
    result = await service.delete_character(session, commands.delete)

    assert result is None
    repo.delete_character.assert_awaited_once_with(session, character)
    assert transaction_events == ["commit"]


async def test_default_image_returns_result_for_requested_character(
    session, transaction_events, character, commands, repo
):
    command = commands.default_image
    repo.set_default_character_image.return_value = CharacterImage(
        id=command.image_id,
        character_id=character.id,
        emotion_tag="happy",
        image_url="existing.png",
        is_default=True,
        created_at=character.created_at,
        updated_at=character.updated_at,
    )

    result = await service.set_default_character_image(session, command)

    assert isinstance(result, types.CharacterImageInfo)
    assert result.is_default
    assert result.id == command.image_id
    repo.set_default_character_image.assert_awaited_once_with(
        session, command.image_id, command.character_id
    )
    assert transaction_events == ["commit"]


@pytest.mark.parametrize("kind", ["image", "asset"])
@pytest.mark.parametrize("found", [True, False])
async def test_media_deletion_is_scoped_to_owned_character(
    session, transaction_events, commands, repo, kind, found
):
    command = getattr(commands, f"delete_{kind}")
    media_id = getattr(command, f"{kind}_id")
    model = CharacterImage if kind == "image" else CharacterAsset
    entity = model(id=media_id, character_id=command.character_id) if found else None
    lookup = getattr(repo, f"get_character_{kind}_by_id_and_character_id")
    lookup.return_value = entity
    delete = getattr(repo, f"delete_character_{kind}")
    function = getattr(service, f"delete_character_{kind}")

    if found:
        assert await function(session, command) is None
        delete.assert_awaited_once_with(session, entity)
        assert transaction_events == ["commit"]
    else:
        with pytest.raises(LookupError):
            await function(session, command)
        delete.assert_not_awaited()
        assert transaction_events == ["rollback"]

    assert lookup.await_args_list == [call(session, media_id, command.character_id)] * (
        2 if found else 1
    )


async def test_missing_or_unrelated_default_image_rolls_back(
    session, transaction_events, commands, repo
):
    repo.set_default_character_image.return_value = None

    with pytest.raises(LookupError, match="Character image not found"):
        await service.set_default_character_image(session, commands.default_image)

    assert transaction_events == ["rollback"]


async def test_repository_failure_propagates_and_rolls_back(
    session, transaction_events, commands, repo
):
    failure = IntegrityError("UPDATE characters", {}, RuntimeError("constraint failed"))
    repo.update_character.side_effect = failure

    with pytest.raises(IntegrityError) as caught:
        await service.update_character(session, commands.update)

    assert caught.value is failure
    assert transaction_events == ["rollback"]
    assert not session.in_transaction()


@pytest.mark.parametrize("kind", ["image", "asset"])
async def test_legacy_media_references_are_added_after_authorization(
    session, transaction_events, commands, repo, kind, monkeypatch, character
):
    model = CharacterImage if kind == "image" else CharacterAsset
    saved = model(
        id=uuid4(),
        character_id=character.id,
        created_at=character.created_at,
        updated_at=character.updated_at,
    )
    persist = AsyncMock(return_value=saved)
    monkeypatch.setattr(repository, "create_media_attachment", persist)
    value = getattr(commands, f"add_{kind}")
    result = await getattr(service, f"add_character_{kind}")(session, value)
    assert result.id == saved.id
    persist.assert_awaited_once_with(session, value, None, kind)
    repo.get_character_by_id_and_owner_id.assert_awaited_once()
    assert transaction_events == ["commit"]
    assert not session.in_transaction()


async def test_existing_transaction_is_not_committed_by_service(
    session, transaction_events, commands, repo
):
    async with session.begin():
        with pytest.raises(InvalidRequestError):
            await service.create_character(session, commands.create)
        repo.create_character.assert_not_awaited()
        assert transaction_events == []
        assert session.in_transaction()
