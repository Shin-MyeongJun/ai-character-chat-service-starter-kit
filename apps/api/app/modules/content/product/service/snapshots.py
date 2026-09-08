"""Publication helpers. Caller owns transaction and locks all source parents first.

Stored media URLs must identify immutable objects. This module does not upload,
copy or delete remote files; physical retention belongs to storage integration.
"""
from uuid import uuid4
from sqlalchemy import func, select
from app.db.models.character import CharacterImage, CharacterAsset
from app.db.models.lorebook import LorebookEntry
from app.db.models.snapshot.character import CharacterSnapshot, CharacterSnapshotImage, CharacterSnapshotAsset
from app.db.models.snapshot.lorebook import LorebookSnapshot


async def next_version(session, cls, column, source_id):
    return (await session.scalar(select(func.max(cls.version)).where(column == source_id)) or 0) + 1


async def freeze_character(session, source):
    snapshot = CharacterSnapshot(id=uuid4(), character_id=source.id,
        version=await next_version(session, CharacterSnapshot, CharacterSnapshot.character_id, source.id), snapshot_schema_version=2,
        snapshot_data={key: getattr(source,key) for key in ('name','description','persona_prompt')})
    session.add(snapshot)
    await session.flush()
    for image in await session.scalars(select(CharacterImage).where(CharacterImage.character_id == source.id).order_by(CharacterImage.id)):
        session.add(CharacterSnapshotImage(character_snapshot_id=snapshot.id, source_image_id=image.id, emotion_tag=image.emotion_tag, image_url=image.image_url, is_default=image.is_default))
    for asset in await session.scalars(select(CharacterAsset).where(CharacterAsset.character_id == source.id).order_by(CharacterAsset.id)):
        session.add(CharacterSnapshotAsset(character_snapshot_id=snapshot.id, source_asset_id=asset.id, asset_type=asset.asset_type, purpose=asset.purpose, file_url=asset.file_url))
    await session.flush()
    return snapshot


async def freeze_lorebook(session, source):
    entries=[]
    for entry in await session.scalars(select(LorebookEntry).where(LorebookEntry.lorebook_id == source.id).order_by(LorebookEntry.id)):
        item = {key: getattr(entry,key) for key in ('title','content','entry_type','activation_type','key_triggers','match_mode','priority','token_budget','placement','is_enabled')}
        item.update(id=str(entry.id), metadata=entry.metadata_)
        entries.append(item)
    snapshot = LorebookSnapshot(id=uuid4(), lorebook_id=source.id,
        version=await next_version(session, LorebookSnapshot, LorebookSnapshot.lorebook_id, source.id), snapshot_schema_version=2,
        snapshot_data={'title':source.title,'description':source.description,'entries':entries})
    session.add(snapshot)
    await session.flush()
    return snapshot


async def media_is_referenced(session, url):
    """Storage cleanup must reject deletion when this returns True."""
    image = await session.scalar(select(CharacterSnapshotImage.id).where(CharacterSnapshotImage.image_url == url).limit(1))
    asset = await session.scalar(select(CharacterSnapshotAsset.id).where(CharacterSnapshotAsset.file_url == url).limit(1))
    return image is not None or asset is not None
