from datetime import UTC, datetime

from sqlalchemy import select

from app.db.models.product_release import ProductReleaseNote, ProductReleaseNoteRevision
from app.db.models.snapshot.character import (
    CharacterSnapshotAsset,
    CharacterSnapshotImage,
)
from app.db.models.snapshot.product import ProductSnapshot, ProductSnapshotCharacter
from app.modules.content.product import repository
from app.modules.content.product.service.publication import build_publication
from app.modules.content.product.types import ReleaseInfo, ReleasePublish


def validate_note(summary, body):
    if (
        not summary.strip()
        or not body.strip()
        or len(summary) > 300
        or len(body) > 20000
    ):
        raise ValueError("Patch summary (1–300) and body (1–20000) are required.")


async def media_manifest(session, sid):
    ids = select(ProductSnapshotCharacter.character_snapshot_id).where(
        ProductSnapshotCharacter.product_snapshot_id == sid
    )
    result = set()
    for i in await session.scalars(
        select(CharacterSnapshotImage).where(
            CharacterSnapshotImage.character_snapshot_id.in_(ids)
        )
    ):
        result.add(("image", str(i.source_image_id), i.emotion_tag, i.image_url))
    for a in await session.scalars(
        select(CharacterSnapshotAsset).where(
            CharacterSnapshotAsset.character_snapshot_id.in_(ids)
        )
    ):
        result.add(
            ("asset", str(a.source_asset_id), a.asset_type, a.purpose, a.file_url)
        )
    return result


async def publish(
    session, *, product_id, owner_id, value: ReleasePublish
) -> ReleaseInfo:
    validate_note(value.summary, value.body)
    async with session.begin():
        product = await repository.owned(session, product_id, owner_id, lock=True)
        previous = (
            await session.get(ProductSnapshot, product.latest_snapshot_id)
            if product.latest_snapshot_id
            else None
        )
        snapshot = await build_publication(
            session, product_id=product_id, owner_id=owner_id
        )
        kind = "initial"
        if previous:
            content_changed = (
                previous.snapshot_data.get("content_digest")
                != snapshot.snapshot_data["content_digest"]
            )
            media_removed = not (await media_manifest(session, previous.id)) <= (
                await media_manifest(session, snapshot.id)
            )
            kind = "content" if content_changed or media_removed else "media"
        policy = "automatic" if kind == "media" and value.auto_apply_media else "choice"
        session.add(
            ProductReleaseNote(
                product_snapshot_id=snapshot.id,
                summary=value.summary,
                body=value.body,
                change_kind=kind,
                update_policy=policy,
            )
        )
        await session.flush()
        return ReleaseInfo(
            snapshot.id, snapshot.version, value.summary, value.body, kind, policy
        )


async def correct_note(
    session, *, product_id, snapshot_id, owner_id, summary, body
) -> ReleaseInfo:
    validate_note(summary, body)
    async with session.begin():
        await repository.owned(session, product_id, owner_id, lock=True)
        snapshot = await session.scalar(
            select(ProductSnapshot).where(
                ProductSnapshot.id == snapshot_id,
                ProductSnapshot.product_id == product_id,
            )
        )
        if snapshot is None:
            raise LookupError("Version not found.")
        note = await session.get(ProductReleaseNote, snapshot_id, with_for_update=True)
        if note is None:
            raise LookupError("Patch note not found.")
        session.add(
            ProductReleaseNoteRevision(
                product_snapshot_id=snapshot_id,
                editor_id=owner_id,
                previous_summary=note.summary,
                previous_body=note.body,
            )
        )
        note.summary, note.body, note.corrected_at = summary, body, datetime.now(UTC)
        await session.flush()
        return ReleaseInfo(
            snapshot.id,
            snapshot.version,
            summary,
            body,
            note.change_kind,
            note.update_policy,
        )
