"""Publish one saved studio revision atomically through public domain services."""

import hashlib
import json
from dataclasses import asdict, dataclass
from uuid import UUID

from app.db.transaction import use_case_transaction
from app.modules.content.character import types as CharacterTypes
from app.modules.content.character.service import command as CharacterCommand
from app.modules.content.character.service import query as CharacterQuery
from app.modules.content.character.service import tags as CharacterTags
from app.modules.content.lorebook import types as LoreTypes
from app.modules.content.lorebook.service import command as LoreCommand
from app.modules.content.product import types as ProductTypes
from app.modules.content.product.service import command as ProductCommand
from app.modules.content.product.service.command import (
    composition as CompositionCommand,
)
from app.modules.content.product.service.command import releases as ReleasesCommand
from app.modules.content.product.service.command import settings as SettingsCommand
from app.modules.content.product.service.command.studio import (
    mark_studio_publication,
)
from app.modules.content.product.service.query.studio import (
    get_studio_draft_for_publication,
)
from app.use_cases.studio_components import component_mapping
from app.use_cases.studio_content import lore_entry_value, scene_entry_value


@dataclass(frozen=True, slots=True)
class PublishStudioCommand:
    product_id: UUID
    owner_id: UUID
    expected_revision: int
    model_id: UUID
    reasoning_effort: str
    summary: str
    body: str


def _publication_content(document: dict) -> tuple[list[dict], list[dict], list[dict], dict]:
    """Validate publishable document structure; every declared image needs managed media."""
    def present_text(value):
        """Reject empty authored text before domain writes begin."""
        return isinstance(value, str) and bool(value.strip())

    work = document.get("work")
    characters = document.get("characters")
    lorebooks = document.get("lorebooks")
    scenes = document.get("scenes")
    if not isinstance(work, dict) or not isinstance(characters, list) or not isinstance(lorebooks, list) or not isinstance(scenes, list):
        raise ValueError("Invalid studio document.")  # noqa: TRY004 - preserve validation contract
    if (not present_text(work.get("title")) or not isinstance(work.get("introduction"), str)
            or not isinstance(work.get("worldRules"), str)
            or not isinstance(work.get("visibility"), str)
            or work["visibility"] not in {"비공개", "링크 공개", "전체 공개"}):
        raise ValueError("Invalid studio work profile.")
    if not characters or not scenes or len(characters) > 100 or len(lorebooks) > 90 or len(scenes) > 100:
        raise ValueError("Publication requires 1–100 characters and start scenes.")
    if any(not isinstance(row, dict) for row in characters + lorebooks + scenes):
        raise ValueError("Invalid studio component.")
    for rows in (characters, lorebooks, scenes):
        ids = [row.get("id") for row in rows]
        if any(not isinstance(value, str) or not value for value in ids) or len(set(ids)) != len(ids):
            raise ValueError("Studio component IDs must be distinct strings.")
    primary_scene = next((row for row in scenes if row.get("id") == work.get("defaultSceneId")), None)
    if primary_scene is None or not primary_scene.get("characterId") or not present_text(primary_scene.get("opening")):
        raise ValueError("Default start scene needs a character and opening.")
    if primary_scene["characterId"] not in {row.get("id") for row in characters}:
        raise ValueError("Default scene character is missing.")
    for character in characters:
        if not present_text(character.get("name")) or not present_text(character.get("persona")):
            raise ValueError("Each character needs a name and persona.")
        if any(not isinstance(character.get(field, ""), str) for field in ("introduction", "dialogue", "relationships", "role")):
            raise ValueError("Invalid studio character text.")
        if not isinstance(character.get("assets", []), list):
            raise ValueError("Invalid studio character assets.")  # noqa: TRY004 - preserve validation contract
        if any(not isinstance(asset, dict) or not asset.get("mediaId") for asset in character.get("assets", [])):
            raise ValueError("Upload character images before publishing this work.")
    for scene in scenes:
        if not present_text(scene.get("title")) or not present_text(scene.get("opening")):
            raise ValueError("Each start scene needs a title and opening.")
        if any(not isinstance(scene.get(field, ""), str) for field in ("background", "initialNotes")):
            raise ValueError("Invalid studio start scene text.")
        if scene.get("characterId") not in {row.get("id") for row in characters}:
            raise ValueError("Each start scene needs a character.")
    for lore in lorebooks:
        if not present_text(lore.get("title")) or not present_text(lore.get("content")):
            raise ValueError("Each lore entry needs a title and content.")
        if not isinstance(lore.get("keywords", []), list) or any(not isinstance(value, str) for value in lore.get("keywords", [])):
            raise ValueError("Invalid studio lore keywords.")
        if lore.get("enabled") and lore.get("activation") == "keyword" and not lore.get("keywords"):
            raise ValueError("Enabled keyword lore needs triggers.")
    for component in (work, *characters, *lorebooks):
        names = component.get("tags", [])
        if not isinstance(names, list) or any(not isinstance(name, str) or not name.strip() for name in names):
            raise ValueError("Studio tags must be a list of nonblank names.")
    return characters, lorebooks, scenes, work


async def publish_studio(session, command: PublishStudioCommand) -> ProductTypes.ReleaseInfo:
    """Publish a saved revision atomically through character/lore/product services.

    Product/draft locks serialize save, upload preparation and publication. Stable
    server copy IDs are retained in the existing receipt JSONB; browser/library IDs
    never authorize server originals. File uploads must already be ready. Domain
    writes, snapshots, mapping and receipt commit together, so a lost response can
    replay even after another revision was saved. Older snapshots are never edited.
    """
    async with use_case_transaction(session):
        draft = await get_studio_draft_for_publication(session, ProductTypes.GetStudioDraftCommand(command.product_id, command.owner_id))
        if draft.revision == command.expected_revision and draft.publication_digest == draft.content_digest and (draft.publication_release or {}).get("snapshot_id") and "_studio" not in draft.publication_release:
            prior = draft.publication_release
            return ProductTypes.ReleaseInfo(UUID(prior["snapshot_id"]), prior["version"], prior["summary"], prior["body"], prior["change_kind"], prior["update_policy"])
        mapping = await component_mapping(session, draft, command.owner_id)
        fingerprint = hashlib.sha256(json.dumps({key: str(value) for key, value in asdict(command).items()}, sort_keys=True).encode()).hexdigest()
        receipt = mapping.get("receipts", {}).get(str(command.expected_revision))
        if receipt:
            if receipt["fingerprint"] != fingerprint:
                raise ProductTypes.StudioDraftConflictError("This revision was published with different request parameters.")
            return ProductTypes.ReleaseInfo(**{**receipt["release"], "snapshot_id": UUID(receipt["release"]["snapshot_id"])})
        if draft.revision != command.expected_revision:
            raise ProductTypes.StudioDraftConflictError("Studio draft changed before publication.")
        if draft.publication_digest == draft.content_digest and (draft.publication_release or {}).get("snapshot_id"):
            prior = draft.publication_release
            return ProductTypes.ReleaseInfo(UUID(prior["snapshot_id"]), prior["version"], prior["summary"], prior["body"], prior["change_kind"], prior["update_policy"])
        characters, lorebooks, scenes, work = _publication_content(draft.document)
        ReleasesCommand.validate_note(command.summary, command.body)
        # Update only work-specific copies. Retained IDs keep product slots stable.
        created_characters = {}
        for row in sorted(characters, key=lambda row: mapping["characters"].get(row["id"], row["id"])):
            prompt = "\n\n".join(part for part in (row["persona"], row.get("dialogue"), row.get("relationships")) if part)
            source = mapping["characters"].get(row["id"])
            if source:
                info = await CharacterCommand.update_character(session, CharacterTypes.UpdateCharacterCommand(character_id=UUID(source), owner_id=command.owner_id, name=row["name"], persona_prompt=prompt, description=row.get("introduction") or None, visibility="private"))
                await CharacterTags.replace_public_tags(session, CharacterTypes.PublicTagsCommand(info.id, command.owner_id, tuple(row.get("tags", ()))))
            else:
                info = await CharacterCommand.create_character(session, CharacterTypes.CreateCharacterCommand(owner_id=command.owner_id, name=row["name"], persona_prompt=prompt, description=row.get("introduction") or None, tags=tuple(row.get("tags", ()))))
                mapping["characters"][row["id"]] = str(info.id)
            created_characters[row["id"]] = info.id
            wanted = set()
            for asset in row.get("assets", []):
                media_id = UUID(asset["mediaId"])
                purpose = "studio:" + asset["id"] + ":" + asset.get("usage", "expression")
                # The public attachment service verifies owner/character/ready state.
                attached = await CharacterCommand.add_character_asset(session, CharacterTypes.CreateCharacterAssetCommand(info.id, command.owner_id, "image", purpose, f"/characters/media/{media_id}/content"))
                wanted.add(attached.id)
            existing_assets = await CharacterQuery.list_character_assets(session, CharacterTypes.ListCharacterAssetsCommand(character_id=info.id))
            for asset in existing_assets:
                if asset.purpose.startswith("studio:") and asset.id not in wanted:
                    await CharacterCommand.delete_character_asset(session, CharacterTypes.DeleteCharacterAssetCommand(info.id, asset.id, command.owner_id))
        if mapping.get("book_id"):
            book_id = UUID(mapping["book_id"])
        else:
            book = await LoreCommand.create_lorebook(session, LoreTypes.CreateLorebookCommand(owner_id=command.owner_id, title=f"{work['title']} · 스튜디오", description=work.get("worldRules") or None, tags=tuple(name for lore in lorebooks for name in lore.get("tags", ()))))
            book_id = book.id
            mapping["book_id"] = str(book_id)
        values = []
        if work.get("worldRules", "").strip():
            values.append(("world_rules", {"title": "세계 규칙", "content": work["worldRules"], "entry_type": "rule", "activation_type": "always", "priority": 100}))
        values.extend(("lore:" + row["id"], lore_entry_value(row)) for row in lorebooks)
        ordered_scenes = sorted(scenes, key=lambda row: row["id"] != work["defaultSceneId"])
        values.extend(("scene:" + row["id"], scene_entry_value(row)) for row in ordered_scenes)
        next_entries = {}
        for key, value in values:
            create_value = LoreTypes.CreateLorebookEntryCommand(lorebook_id=book_id, owner_id=command.owner_id, **value)
            if key in mapping["entries"]:
                entry = await LoreCommand.update_lorebook_entry(session, LoreTypes.UpdateLorebookEntryCommand(entry_id=UUID(mapping["entries"][key]), **asdict(create_value)))
            else:
                entry = await LoreCommand.create_lorebook_entry(session, create_value)
            next_entries[key] = str(entry.id)
        # Detach start settings first so removed start entries do not violate FKs.
        start_ids = tuple(UUID(next_entries["scene:" + row["id"]]) for row in ordered_scenes)
        await CompositionCommand.replace_composition(session, ProductTypes.ReplaceCompositionCommand(product_id=command.product_id, owner_id=command.owner_id, value=ProductTypes.ProductCompositionInfo(characters=tuple(ProductTypes.CharacterSelection(created_characters[row["id"]], row["id"] == ordered_scenes[0]["characterId"], row.get("role") or None) for row in characters), lorebooks=(ProductTypes.LorebookSelection(book_id, role="main"),))))
        await SettingsCommand.set_settings(session, ProductTypes.SetSettingsCommand(product_id=command.product_id, owner_id=command.owner_id, value=ProductTypes.ProductSettingsInfo(model_id=command.model_id, reasoning_effort=command.reasoning_effort, start_entry_ids=start_ids)))
        for key, entry_id in mapping["entries"].items():
            if key not in next_entries:
                await LoreCommand.delete_lorebook_entry(session, LoreTypes.DeleteLorebookEntryCommand(book_id, UUID(entry_id), command.owner_id))
        mapping["entries"] = next_entries
        visibility = {"비공개": "private", "링크 공개": "unlisted", "전체 공개": "public"}[work["visibility"]]
        await ProductCommand.update_product(session, ProductTypes.UpdateProductCommand(product_id=command.product_id, owner_id=command.owner_id, value=ProductTypes.ProductProfileCommand(work["title"], work.get("introduction") or None, ordered_scenes[0]["opening"], visibility), tags=tuple(work["tags"]) if "tags" in work else None))
        release = await ReleasesCommand.publish_product(session, ProductTypes.PublishCommand(product_id=command.product_id, owner_id=command.owner_id, value=ProductTypes.ReleaseNoteCommand(command.summary, command.body)))
        mapping.setdefault("receipts", {})[str(command.expected_revision)] = {"fingerprint": fingerprint, "release": {**asdict(release), "snapshot_id": str(release.snapshot_id)}}
        await mark_studio_publication(session, ProductTypes.MarkStudioPublicationCommand(command.product_id, command.owner_id, draft.content_digest, release, mapping))
        return release
