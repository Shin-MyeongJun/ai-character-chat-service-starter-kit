"""Publish one saved studio revision atomically through public domain services."""

from dataclasses import dataclass
from uuid import UUID

from app.db.transaction import use_case_transaction
from app.modules.content.character import types as CharacterTypes
from app.modules.content.character.service import command as CharacterCommand
from app.modules.content.lorebook import types as LoreTypes
from app.modules.content.lorebook.service import command as LoreCommand
from app.modules.content.product import types as ProductTypes
from app.modules.content.product.service.command import composition as CompositionCommand
from app.modules.content.product.service.command import releases as ReleasesCommand
from app.modules.content.product.service.command import settings as SettingsCommand
from app.modules.content.product.service.command.studio import mark_studio_publication
from app.modules.content.product.service.query.studio import get_studio_draft_for_publication
from app.modules.content.product.service import query as ProductQuery


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
    def present_text(value):
        return isinstance(value, str) and bool(value.strip())

    work = document.get("work")
    characters = document.get("characters")
    lorebooks = document.get("lorebooks")
    scenes = document.get("scenes")
    if not isinstance(work, dict) or not isinstance(characters, list) or not isinstance(lorebooks, list) or not isinstance(scenes, list):
        raise ValueError("Invalid studio document.")
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
            raise ValueError("Invalid studio character assets.")
        if character.get("assets"):
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
    return characters, lorebooks, scenes, work


async def publish_studio(session, command: PublishStudioCommand) -> ProductTypes.ReleaseInfo:
    async with use_case_transaction(session):
        draft = await get_studio_draft_for_publication(
            session, ProductTypes.GetStudioDraftCommand(command.product_id, command.owner_id)
        )
        if draft.revision != command.expected_revision:
            raise ProductTypes.StudioDraftConflictError("Studio draft changed before publication.")
        if draft.publication_digest == draft.content_digest and draft.publication_release:
            prior = draft.publication_release
            return ProductTypes.ReleaseInfo(
                UUID(prior["snapshot_id"]), prior["version"], prior["summary"],
                prior["body"], prior["change_kind"], prior["update_policy"],
            )
        if draft.publication_release:
            raise ProductTypes.StudioDraftConflictError("Publish updates through the product release workflow.")
        characters, lorebooks, scenes, work = _publication_content(draft.document)
        profile = await ProductQuery.get_owned_product(
            session, ProductTypes.OwnedProductCommand(command.product_id, command.owner_id)
        )
        opening = next(scene["opening"] for scene in scenes if scene["id"] == work["defaultSceneId"])
        visibility = {"비공개": "private", "링크 공개": "unlisted", "전체 공개": "public"}[work["visibility"]]
        if (profile.title, profile.description, profile.opening_message, profile.visibility) != (
            work["title"], work.get("introduction") or None, opening, visibility
        ):
            raise ProductTypes.StudioDraftConflictError("Product profile changed after the studio draft was saved.")
        created_characters: dict[str, UUID] = {}
        for character in characters:
            prompt = "\n\n".join(part for part in (
                character["persona"], character.get("dialogue"), character.get("relationships")
            ) if part)
            info = await CharacterCommand.create_character(session, CharacterTypes.CreateCharacterCommand(
                owner_id=command.owner_id, name=character["name"],
                persona_prompt=prompt, description=character.get("introduction") or None,
            ))
            created_characters[character["id"]] = info.id
        book = await LoreCommand.create_lorebook(session, LoreTypes.CreateLorebookCommand(
            owner_id=command.owner_id, title=f"{work['title']} · 스튜디오", description=work.get("worldRules") or None,
        ))
        entry_types = {"장소": "location", "세계관": "world", "인물": "character_relation", "사건": "event"}
        priorities = {"필수": 100, "높음": 75, "보통": 50, "낮음": 25}
        if str(work.get("worldRules") or "").strip():
            await LoreCommand.create_lorebook_entry(session, LoreTypes.CreateLorebookEntryCommand(
                lorebook_id=book.id, owner_id=command.owner_id, title="세계 규칙",
                content=work["worldRules"], entry_type="rule", activation_type="always",
                priority=100, is_enabled=True,
            ))
        for lore in lorebooks:
            await LoreCommand.create_lorebook_entry(session, LoreTypes.CreateLorebookEntryCommand(
                lorebook_id=book.id, owner_id=command.owner_id, title=lore["title"], content=lore["content"],
                entry_type=entry_types.get(lore.get("category"), "world"),
                activation_type=lore.get("activation", "always"),
                key_triggers=lore.get("keywords") or None,
                priority=priorities.get(lore.get("priority"), 50),
                token_budget=lore.get("tokenBudget"),
                placement="before_history" if lore.get("placement") == "before" else "after_memory",
                is_enabled=bool(lore.get("enabled", True)),
            ))
        start_ids: list[UUID] = []
        for scene in scenes:
            content = "\n\n".join(part for part in (scene.get("background"), scene.get("opening"), scene.get("initialNotes")) if part)
            entry = await LoreCommand.create_lorebook_entry(session, LoreTypes.CreateLorebookEntryCommand(
                lorebook_id=book.id, owner_id=command.owner_id, title=scene["title"], content=content,
                entry_type="start_set", activation_type="always", is_enabled=True,
            ))
            start_ids.append(entry.id)
        await CompositionCommand.replace_composition(session, ProductTypes.ReplaceCompositionCommand(
            product_id=command.product_id, owner_id=command.owner_id,
            value=ProductTypes.ProductCompositionInfo(
                characters=tuple(ProductTypes.CharacterSelection(
                    character_id=created_characters[row["id"]],
                    is_primary=row["id"] == next(scene for scene in scenes if scene["id"] == work["defaultSceneId"])["characterId"],
                    role_name=row.get("role") or None,
                ) for row in characters),
                lorebooks=(ProductTypes.LorebookSelection(lorebook_id=book.id, role="main"),),
            ),
        ))
        await SettingsCommand.set_settings(session, ProductTypes.SetSettingsCommand(
            product_id=command.product_id, owner_id=command.owner_id,
            value=ProductTypes.ProductSettingsInfo(
                model_id=command.model_id, reasoning_effort=command.reasoning_effort,
                start_entry_ids=tuple(start_ids),
            ),
        ))
        release = await ReleasesCommand.publish_product(session, ProductTypes.PublishCommand(
            product_id=command.product_id, owner_id=command.owner_id,
            value=ProductTypes.ReleaseNoteCommand(command.summary, command.body),
        ))
        await mark_studio_publication(session, ProductTypes.MarkStudioPublicationCommand(
            command.product_id, command.owner_id, draft.content_digest, release,
        ))
        return release
