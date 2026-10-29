"""Stable studio copy identities and upload preparation through public services."""

from copy import deepcopy
from typing import NotRequired, TypedDict, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.transaction import use_case_transaction
from app.modules.content.character import types as CharacterTypes
from app.modules.content.character.service import command as CharacterCommand
from app.modules.content.lorebook import types as LoreTypes
from app.modules.content.lorebook.service import query as LoreQuery
from app.modules.content.product import types as ProductTypes
from app.modules.content.product.service.command import studio as StudioCommand
from app.modules.content.product.service.query.composition import get_composition
from app.modules.content.product.service.query.studio import (
    get_studio_draft_for_publication,
)
from app.use_cases.studio_content import StudioDocument


class StoredRelease(TypedDict):
    snapshot_id: str
    version: int
    summary: str
    body: str
    change_kind: str
    update_policy: str


class StudioReceipt(TypedDict):
    fingerprint: str
    release: StoredRelease


class StudioMapping(TypedDict):
    characters: dict[str, str]
    entries: dict[str, str]
    receipts: dict[str, StudioReceipt]
    book_id: NotRequired[str]


class PreparedComponents(TypedDict):
    characters: dict[str, str]


async def component_mapping(
    session: AsyncSession, draft: ProductTypes.StudioDraftInfo, owner_id: UUID
) -> StudioMapping:
    """Adopt pre-mapping publications from the still-saved original document.

    Product order identifies characters; unique entry titles identify legacy lore.
    Ambiguous legacy titles are rejected instead of inventing source identities.
    The caller holds product/draft locks and persists this mapping before edits.
    """
    prior = draft.publication_release or {}
    if "_studio" in prior:
        # This private receipt member is written by these studio use cases.
        # Preserve deepcopy and malformed legacy data rather than repairing it.
        return cast(StudioMapping, deepcopy(prior["_studio"]))
    mapping: StudioMapping = {"characters": {}, "entries": {}, "receipts": {}}
    if not prior.get("snapshot_id"):
        return mapping
    composition = await get_composition(
        session,
        ProductTypes.GetCompositionCommand(
            product_id=draft.product_id, owner_id=owner_id
        ),
    )
    # Saved editor JSON retains its existing structural assumptions and errors.
    document = cast(StudioDocument, draft.document)
    characters = document["characters"]
    if (
        len(characters) != len(composition.characters)
        or len(composition.lorebooks) != 1
    ):
        raise ProductTypes.StudioDraftConflictError(
            "Legacy studio composition needs explicit identity migration."
        )
    mapping["characters"] = {
        row["id"]: str(link.character_id)
        for row, link in zip(characters, composition.characters, strict=True)
    }
    book_id = composition.lorebooks[0].lorebook_id
    mapping["book_id"] = str(book_id)
    entries: list[LoreTypes.LorebookEntryInfo] = []
    cursor: LoreTypes.LorebookCursor | None = None
    while True:
        page = await LoreQuery.list_lorebook_entries_by_owner_id(
            session,
            LoreTypes.ListLorebookEntriesByOwnerIdCommand(
                lorebook_id=book_id, owner_id=owner_id, cursor=cursor, limit=100
            ),
        )
        if page is None:
            raise LookupError("Studio lorebook not found.")
        entries.extend(page.items)
        cursor = page.next_cursor
        if cursor is None:
            break
    expected = (
        [("world_rules", "세계 규칙")]
        if document["work"].get("worldRules", "").strip()
        else []
    )
    expected += [("lore:" + row["id"], row["title"]) for row in document["lorebooks"]]
    expected += [("scene:" + row["id"], row["title"]) for row in document["scenes"]]
    for key, title in expected:
        candidates = [
            entry
            for entry in entries
            if entry.title == title
            and (entry.entry_type == "start_set") == key.startswith("scene:")
        ]
        if len(candidates) != 1:
            raise ProductTypes.StudioDraftConflictError(
                "Legacy lore titles are ambiguous; explicit identity migration is required."
            )
        mapping["entries"][key] = str(candidates[0].id)
    return mapping


async def save_studio(
    session: AsyncSession, command: ProductTypes.SaveStudioDraftCommand
) -> ProductTypes.StudioDraftInfo:
    """Preserve legacy copy identities before CAS-saving an edited document.

    One transaction owns product → draft locks, adoption and the document write.
    No files or external services are called; a conflict rolls back every write.
    """
    async with use_case_transaction(session):
        if command.expected_revision is not None:
            draft = await get_studio_draft_for_publication(
                session,
                ProductTypes.GetStudioDraftCommand(
                    command.product_id, command.owner_id
                ),
            )
            if draft.publication_release and "_studio" not in draft.publication_release:
                mapping = await component_mapping(session, draft, command.owner_id)
                # TypedDict and recursive JSON describe the same in-memory mapping.
                await StudioCommand.set_studio_components(
                    session,
                    ProductTypes.SetStudioComponentsCommand(
                        command.product_id,
                        command.owner_id,
                        draft.revision,
                        cast(ProductTypes.ProductJsonObject, mapping),
                    ),
                )
        return await StudioCommand.save_studio_draft(session, command)


async def prepare_components(
    session: AsyncSession,
    command: ProductTypes.GetStudioDraftCommand,
    expected_revision: int,
) -> PreparedComponents:
    """Commit reusable work-specific characters before a separate media upload.

    Uploaded objects have their own durable workflow; preparation does not publish
    or freeze anything. Response-loss retry reuses the persisted local-ID mapping.
    """
    async with use_case_transaction(session):
        draft = await get_studio_draft_for_publication(session, command)
        if draft.revision != expected_revision:
            raise ProductTypes.StudioDraftConflictError(
                "Studio draft changed before upload preparation."
            )
        mapping = await component_mapping(session, draft, command.owner_id)
        # Upload preparation uses the saved editor fields, without new validation.
        document = cast(StudioDocument, draft.document)
        for row in document.get("characters", []):
            if row["id"] not in mapping["characters"]:
                info = await CharacterCommand.create_character(
                    session,
                    CharacterTypes.CreateCharacterCommand(
                        owner_id=command.owner_id,
                        name=row["name"],
                        persona_prompt=row["persona"],
                        description=row.get("introduction") or None,
                    ),
                )
                mapping["characters"][row["id"]] = str(info.id)
        # Keep this exact mutable mapping and its extensions at the JSON boundary.
        await StudioCommand.set_studio_components(
            session,
            ProductTypes.SetStudioComponentsCommand(
                command.product_id,
                command.owner_id,
                draft.revision,
                cast(ProductTypes.ProductJsonObject, mapping),
            ),
        )
        return {"characters": mapping["characters"]}
