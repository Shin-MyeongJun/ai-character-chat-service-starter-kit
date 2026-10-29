"""Publication comparison values and detached snapshot data retain their contracts."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.snapshot.character import (
    CharacterSnapshot,
    CharacterSnapshotAsset,
    CharacterSnapshotImage,
)
from app.modules.content.character import repository, types
from app.modules.content.character.mapper import persistence


@pytest.mark.asyncio
@pytest.mark.parametrize("description", [None, ""])
async def test_freeze_snapshot_keeps_v2_body_and_optional_description(
    description: str | None,
) -> None:
    now = datetime.now(UTC)
    source = types.CharacterInfo(
        id=uuid4(),
        owner_id=uuid4(),
        name="Original name",
        description=description,
        persona_prompt="Unmodified persona\n",
        visibility="private",
        status="draft",
        default_model_id=uuid4(),
        created_at=now,
        updated_at=now,
    )
    session = AsyncMock(spec=AsyncSession)
    session.scalar.return_value = 4
    session.scalars.return_value = []

    snapshot = await repository.freeze_character(session, source)
    info = persistence.character_snapshot_entity_to_info(snapshot)

    assert snapshot.character_id == source.id
    assert snapshot.version == 5
    assert snapshot.snapshot_schema_version == 2
    # Account, moderation and model-selection fields are not publication data.
    assert snapshot.snapshot_data == {
        "name": "Original name",
        "description": description,
        "persona_prompt": "Unmodified persona\n",
    }
    assert info.snapshot_data == snapshot.snapshot_data
    assert info.snapshot_data is not snapshot.snapshot_data


def test_snapshot_info_preserves_deleted_source_and_isolates_nested_json():
    snapshot = CharacterSnapshot(
        id=uuid4(),
        character_id=None,
        version=3,
        snapshot_data={
            "name": "Original",
            "description": None,
            "persona_prompt": "Persona",
            "extension": {"labels": ["original"]},
        },
    )

    info = persistence.character_snapshot_entity_to_info(snapshot)

    assert info.id == snapshot.id
    assert info.character_id is None
    assert info.version == 3
    assert info.snapshot_data == snapshot.snapshot_data
    info.snapshot_data["extension"]["labels"].append("info only")
    assert snapshot.snapshot_data["extension"]["labels"] == ["original"]
    snapshot.snapshot_data["extension"]["labels"].append("entity only")
    assert info.snapshot_data["extension"]["labels"] == ["original", "info only"]


def test_snapshot_manifest_retains_release_comparison_identity():
    image = CharacterSnapshotImage(
        source_image_id=uuid4(),
        emotion_tag="happy",
        image_url="https://example.test/image.png",
        is_default=False,
    )
    asset = CharacterSnapshotAsset(
        source_asset_id=uuid4(),
        asset_type="audio",
        purpose="greeting",
        file_url="https://example.test/audio.mp3",
    )
    row = repository.SnapshotMediaRow(images=[image, image], assets=[asset])

    before = persistence.snapshot_media_row_to_info(row).manifest

    assert before == frozenset(
        {
            ("image", str(image.source_image_id), "happy", image.image_url),
            ("asset", str(asset.source_asset_id), "audio", "greeting", asset.file_url),
        }
    )
    # Release comparisons deliberately ignore default selection and duplicate entries.
    image.is_default = True
    assert persistence.snapshot_media_row_to_info(row).manifest == before
    asset.file_url = "https://example.test/replaced.mp3"
    after = persistence.snapshot_media_row_to_info(row).manifest
    assert not before <= after
    assert (
        persistence.snapshot_media_row_to_info(
            repository.SnapshotMediaRow(images=[], assets=[])
        ).manifest
        == frozenset()
    )
