from datetime import UTC, datetime

from app.db.transaction import use_case_transaction
from app.modules.content.character import types as CharacterTypes
from app.modules.content.character.service import query as CharacterQueryService
from app.modules.content.product import repository as Repository
from app.modules.content.product import types as Types
from app.modules.content.product.mapper import persistence as PersistenceMapper
from app.modules.content.product.service import query as QueryService
from app.modules.content.product.service.command.publication import _build_publication
from app.modules.content.product.types import ReleaseInfo


def validate_note(summary, body):
    if (
        not summary.strip()
        or not body.strip()
        or len(summary) > 300
        or (len(body) > 20000)
    ):
        raise ValueError("Patch summary (1–300) and body (1–20000) are required.")


async def _get_media_manifest(session, sid):
    ids = await Repository.list_snapshot_character_ids(session, sid)
    info = await CharacterQueryService.get_snapshot_media(
        session, CharacterTypes.GetSnapshotMediaCommand(ids)
    )
    return info.manifest


async def publish_product(session, command: Types.PublishCommand) -> ReleaseInfo:
    product_id = command.product_id
    owner_id = command.owner_id
    value = command.value
    validate_note(value.summary, value.body)
    async with use_case_transaction(session):
        product = await QueryService.get_owned_product(
            session, Types.OwnedProductCommand(product_id, owner_id, lock=True)
        )
        previous = (
            await QueryService.get_product_snapshot(
                session, Types.ProductSnapshotCommand(product.latest_snapshot_id)
            )
            if product.latest_snapshot_id
            else None
        )
        snapshot = await _build_publication(
            session,
            Types.BuildPublicationCommand(product_id=product_id, owner_id=owner_id),
        )
        kind = "initial"
        if previous:
            content_changed = (
                previous.snapshot_data.get("content_digest")
                != snapshot.snapshot_data["content_digest"]
            )
            media_removed = not await _get_media_manifest(
                session, previous.id
            ) <= await _get_media_manifest(session, snapshot.id)
            kind = "content" if content_changed or media_removed else "media"
        policy = "automatic" if kind == "media" and value.auto_apply_media else "choice"
        await Repository.create_release_note(
            session, snapshot.id, value.summary, value.body, kind, policy
        )
        return ReleaseInfo(
            snapshot.id, snapshot.version, value.summary, value.body, kind, policy
        )


async def correct_note(session, command: Types.CorrectNoteCommand) -> ReleaseInfo:
    product_id = command.product_id
    snapshot_id = command.snapshot_id
    owner_id = command.owner_id
    summary = command.summary
    body = command.body
    validate_note(summary, body)
    async with use_case_transaction(session):
        await QueryService.get_owned_product(
            session, Types.OwnedProductCommand(product_id, owner_id, lock=True)
        )
        snapshot = await QueryService.get_product_snapshot(
            session, Types.ProductSnapshotCommand(snapshot_id)
        )
        if snapshot.product_id != product_id:
            raise LookupError("Version not found.")
        row = await Repository.get_release_note(session, snapshot_id, lock=True)
        note = PersistenceMapper.release_note_entity_to_info(row)
        if note is None:
            raise LookupError("Patch note not found.")
        await Repository.correct_release_note(
            session, snapshot_id, owner_id, summary, body, datetime.now(UTC)
        )
        return ReleaseInfo(
            snapshot.id,
            snapshot.version,
            summary,
            body,
            note.change_kind,
            note.update_policy,
        )
