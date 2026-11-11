"""Owner-scoped studio document writes with optimistic concurrency."""

import hashlib
import json
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.idempotency import lock_key
from app.db.transaction import use_case_transaction
from app.modules.content.product import repository as Repository
from app.modules.content.product import types as Types
from app.modules.content.product.mapper import persistence as PersistenceMapper
from app.modules.content.product.service.command import (
    file_versions as FileVersionsCommandService,
)
from app.modules.content.product.service.studio_images import (
    get_retired_studio_image_ids,
    get_studio_image_ids,
    normalize_studio_chat_images,
)
from app.modules.content.product.service.studio_validation import (
    validate_studio_document_shape,
)


def _read_studio_tag_names(value: object) -> tuple[str, ...]:
    """Narrow the JSON sequence shape; the shared tag service validates names."""
    if not isinstance(value, (list, tuple)):
        raise ValueError("Tag names must be nonblank strings.")
    names: list[str] = []
    for name in value:
        if not isinstance(name, str):
            raise ValueError("Tag names must be nonblank strings.")
        names.append(name)
    return tuple(names)


async def _sync_studio_file_references(
    session: AsyncSession,
    product_id: UUID,
    previous: set[UUID],
    current: set[UUID],
) -> None:
    for file_id in sorted(previous | current):
        reference = Types.ProductFileReferenceCommand(
            product_id=product_id,
            file_version_id=file_id,
            kind="draft",
            reference_id=product_id,
        )
        if file_id in current:
            await FileVersionsCommandService.retain_product_file_version(
                session, reference
            )
        else:
            await FileVersionsCommandService.release_product_file_version(
                session, reference
            )


async def save_studio_draft(
    session: AsyncSession, command: Types.SaveStudioDraftCommand
) -> Types.StudioDraftInfo:
    """CAS-save editor JSON; published profile and approval remain untouched until release."""
    raw = json.dumps(
        command.document, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    if len(raw) > 2 * 1024 * 1024 or command.document.get("version") != 2:
        raise ValueError("Invalid or oversized studio document.")
    if command.expected_revision is not None and command.expected_revision < 1:
        raise ValueError("Invalid studio revision.")
    validate_studio_document_shape(command.document)
    document = normalize_studio_chat_images(command.document)
    if document != command.document:
        raw = json.dumps(
            document, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    work = document.get("work")
    if not isinstance(work, dict):
        raise ValueError("Studio work profile is required.")
    title = work.get("title")
    description = work.get("introduction")
    # Shape validation guarantees text before the label lookup.
    visibility_by_label: dict[object, Types.Visibility] = {
        "비공개": "private",
        "링크 공개": "unlisted",
        "전체 공개": "public",
    }
    visibility = visibility_by_label.get(work.get("visibility"))
    if (
        not isinstance(title, str)
        or not 1 <= len(title.strip()) <= 200
        or not isinstance(description, str)
        or len(description) > 20000
        or visibility is None
    ):
        raise ValueError("Invalid studio work profile.")
    scenes = document.get("scenes")
    if not isinstance(scenes, list):
        raise ValueError("Studio scenes are required.")
    default_scene = next(
        (
            scene
            for scene in scenes
            if isinstance(scene, dict) and scene.get("id") == work.get("defaultSceneId")
        ),
        None,
    )
    opening = default_scene.get("opening") if default_scene else None
    if opening is not None and (not isinstance(opening, str) or len(opening) > 20000):
        raise ValueError("Invalid studio opening.")
    profile = Types.ProductProfileCommand(
        title=title,
        description=description or None,
        opening_message=opening,
        visibility=visibility,
    )
    digest = hashlib.sha256(raw).hexdigest()
    async with use_case_transaction(session):
        await lock_key(session, "product-studio-draft", str(command.product_id))
        product_row = await Repository.get_product_for_update(
            session, command.product_id
        )
        product = PersistenceMapper.product_entity_to_state_info(product_row)
        if product is None:
            if command.expected_revision is not None:
                raise Types.StudioDraftConflictError("Studio product was removed.")
            await Repository.create_product(
                session, command.owner_id, profile, product_id=command.product_id
            )
        elif product.owner_id != command.owner_id:
            raise LookupError("Product not found.")
        existing_row = await Repository.get_studio_draft(
            session, command.product_id, lock=True
        )
        existing = PersistenceMapper.studio_draft_entity_to_info(existing_row)
        if existing is not None and existing.content_digest == digest:
            return existing
        if (existing.revision if existing else None) != command.expected_revision:
            raise Types.StudioDraftConflictError("Studio draft changed on the server.")
        previous_document = existing.document if existing else {}
        previous_items = get_studio_image_ids(previous_document, "imageItemId")
        current_items = get_studio_image_ids(document, "imageItemId")
        retired = get_retired_studio_image_ids(previous_document)
        if current_items & retired:
            raise ValueError("A deleted studio image item ID cannot be reused.")
        retired.update(previous_items - current_items)
        if retired:
            document[Types.RETIRED_STUDIO_IMAGE_ITEMS] = [
                str(item_id) for item_id in sorted(retired)
            ]
        await _sync_studio_file_references(
            session,
            command.product_id,
            get_studio_image_ids(previous_document, "fileVersionId"),
            get_studio_image_ids(document, "fileVersionId"),
        )
        if product is not None and product.latest_snapshot_id is None:
            await Repository.update_product(
                session, command.product_id, command.owner_id, profile
            )
        if "tags" in work and (product is None or product.latest_snapshot_id is None):
            from app.modules.content.product.service import tags as TagsCommandService

            await TagsCommandService.replace_public_tags(
                session,
                Types.PublicTagsCommand(
                    target_id=command.product_id,
                    user_id=command.owner_id,
                    names=_read_studio_tag_names(work["tags"]),
                ),
            )
        row = await Repository.save_studio_draft(
            session,
            command.product_id,
            (existing.revision + 1) if existing else 1,
            digest,
            document,
            existing_row,
        )
        result = PersistenceMapper.studio_draft_entity_to_info(row)
        # Creation/update or receipt metadata writes do not delete the locked row.
        assert result is not None, "Locked studio draft disappeared."
        return result


async def mark_studio_publication(
    session: AsyncSession, command: Types.MarkStudioPublicationCommand
) -> Types.ReleaseInfo:
    """Record the committed release receipt and stable component mapping in existing JSONB."""
    async with use_case_transaction(session):
        await lock_key(session, "product-studio-draft", str(command.product_id))
        product = PersistenceMapper.product_entity_to_state_info(
            await Repository.get_product_for_update(session, command.product_id)
        )
        if product is None or product.owner_id != command.owner_id:
            raise LookupError("Product not found.")
        row = await Repository.get_studio_draft(session, command.product_id, lock=True)
        draft = PersistenceMapper.studio_draft_entity_to_info(row)
        if draft is None or draft.content_digest != command.content_digest:
            raise Types.StudioDraftConflictError(
                "Studio draft changed before publication."
            )
        release = command.release
        await Repository.mark_studio_publication(
            session,
            row,
            command.content_digest,
            {
                "snapshot_id": str(release.snapshot_id),
                "version": release.version,
                "summary": release.summary,
                "body": release.body,
                "change_kind": release.change_kind,
                "update_policy": release.update_policy,
                "_studio": command.mapping or {},
            },
        )
        return release


async def set_studio_components(
    session: AsyncSession, command: Types.SetStudioComponentsCommand
) -> Types.StudioDraftInfo:
    """Persist server-owned component identities without changing document revision/digest.

    The upper workflow owns the transaction and advisory → product → draft order. Keeping
    upload preparation here makes response-loss retries reuse the same characters.
    """
    async with use_case_transaction(session):
        await lock_key(session, "product-studio-draft", str(command.product_id))
        product = PersistenceMapper.product_entity_to_state_info(
            await Repository.get_product_for_update(session, command.product_id)
        )
        if product is None or product.owner_id != command.owner_id:
            raise LookupError("Product not found.")
        row = await Repository.get_studio_draft(session, command.product_id, lock=True)
        draft = PersistenceMapper.studio_draft_entity_to_info(row)
        if draft is None or draft.revision != command.expected_revision:
            raise Types.StudioDraftConflictError(
                "Studio draft changed before component preparation."
            )
        receipt = {**(draft.publication_release or {}), "_studio": command.mapping}
        await Repository.mark_studio_publication(
            session, row, draft.publication_digest, receipt
        )
        result = PersistenceMapper.studio_draft_entity_to_info(row)
        # Creation/update or receipt metadata writes do not delete the locked row.
        assert result is not None, "Locked studio draft disappeared."
        return result
