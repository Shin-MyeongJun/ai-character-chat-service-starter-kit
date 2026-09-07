from datetime import UTC, datetime
from uuid import uuid4

import pytest
from app.modules.lorebook import schemas, types
from app.modules.lorebook.mapper.schema import LorebookSchemaMapper
from app.modules.lorebook.router import router
from pydantic import ValidationError


@pytest.mark.parametrize(
    "values",
    [
        {"cursor_id": uuid4()},
        {"cursor_created_at": datetime.now(UTC)},
        {
            "cursor_created_at": datetime.now(UTC).replace(tzinfo=None),
            "cursor_id": uuid4(),
        },
    ],
)
def test_cursor_requires_a_complete_timezone_aware_pair(values):
    with pytest.raises(ValidationError):
        schemas.ListLorebooksRequestDto.model_validate(values)


def test_cursor_mapper_preserves_valid_cursor():
    created_at = datetime.now(UTC)
    cursor_id = uuid4()
    request = schemas.ListLorebookEntriesRequestDto(
        cursor_created_at=created_at,
        cursor_id=cursor_id,
    )

    result = LorebookSchemaMapper.cursor_request_to_value(request)

    assert result == types.LorebookCursor(created_at=created_at, id=cursor_id)


def test_create_mapper_uses_trusted_owner_id():
    untrusted_owner_id = uuid4()
    trusted_owner_id = uuid4()
    request = schemas.CreateLorebookRequestDto.model_validate(
        {"title": "World guide", "owner_id": str(untrusted_owner_id)}
    )

    result = LorebookSchemaMapper.create_lorebook_request_to_command(
        request,
        trusted_owner_id,
    )

    assert result.owner_id == trusted_owner_id
    assert result.status == "draft"


def test_entry_response_excludes_embedding_and_maps_metadata():
    now = datetime.now(UTC)
    value = types.LorebookEntryInfo(
        id=uuid4(),
        lorebook_id=uuid4(),
        title="Northern forest",
        content="The forest is sealed.",
        entry_type="location",
        activation_type="keyword",
        key_triggers=["northern forest"],
        match_mode="contains",
        priority=10,
        token_budget=100,
        placement="before_history",
        is_enabled=True,
        metadata={"chapter": 2},
        created_at=now,
        updated_at=now,
    )

    response = LorebookSchemaMapper.entry_info_to_response(value)

    assert response.metadata == {"chapter": 2}
    assert "embedding" not in response.model_dump()


def test_enabled_keyword_entry_requires_a_trigger():
    with pytest.raises(ValidationError, match="at least one trigger"):
        schemas.CreateLorebookEntryRequestDto(
            lorebook_id=uuid4(),
            content="A keyword entry",
            activation_type="keyword",
        )

    default_entry = schemas.CreateLorebookEntryRequestDto(
        lorebook_id=uuid4(),
        content="An always-on entry",
    )
    assert default_entry.activation_type == "always"
    assert default_entry.key_triggers is None

    disabled_keyword = schemas.CreateLorebookEntryRequestDto(
        lorebook_id=uuid4(),
        content="An unfinished keyword entry",
        activation_type="keyword",
        is_enabled=False,
    )
    assert disabled_keyword.key_triggers is None


def test_static_me_routes_are_registered_before_uuid_routes():
    paths = [route.path for route in router.routes]

    assert paths.index("/lorebooks/me") < paths.index("/lorebooks/{lorebook_id}")
