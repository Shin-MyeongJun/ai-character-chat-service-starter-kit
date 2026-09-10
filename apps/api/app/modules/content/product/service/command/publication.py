"Internal atomic publication builder; public command adds required release notes."

import hashlib
import json

from app.modules.content.character import types as CharacterTypes
from app.modules.content.character.service import command as CharacterCommandService
from app.modules.content.character.service import query as CharacterQueryService
from app.modules.content.lorebook import types as LorebookTypes
from app.modules.content.lorebook.service import command as LorebookCommandService
from app.modules.content.lorebook.service import query as LorebookQueryService
from app.modules.content.product import repository as Repository
from app.modules.content.product import types as Types
from app.modules.content.product.mapper import persistence as PersistenceMapper
from app.modules.content.product.service import query as QueryService
from app.modules.content.product.service.command import (
    settings as SettingsCommandService,
)
from app.modules.llm import types as LlmTypes
from app.modules.llm.service import query as LlmQueryService


async def _build_publication(
    session, command: Types.BuildPublicationCommand
) -> Types.ProductSnapshotInfo:
    """Caller must own a transaction. Product/source locks serialize all publication reads."""
    product_id = command.product_id
    owner_id = command.owner_id
    if not session.in_transaction():
        raise RuntimeError("Publication requires a caller transaction.")
    product = await QueryService.get_owned_product(
        session, Types.OwnedProductCommand(product_id, owner_id, lock=True)
    )
    row = await Repository.get_product_composition(session, product_id)
    composition = PersistenceMapper.product_composition_row_to_state_info(row)
    char_links, book_links, targets = (
        composition.characters,
        sorted(composition.books, key=lambda b: b.id),
        composition.targets,
    )
    await CharacterQueryService.get_owned_characters(
        session,
        CharacterTypes.GetOwnedCharactersCommand(
            tuple(c.character_id for c in char_links), owner_id, lock=True
        ),
    )
    await LorebookQueryService.get_owned_lorebooks(
        session,
        LorebookTypes.GetOwnedLorebooksCommand(
            tuple(b.lorebook_id for b in book_links), owner_id, lock=True
        ),
    )
    _, starts = await SettingsCommandService._validate_publication(session, product)
    model = await SettingsCommandService._validate_model(
        session, product.default_model_id, product.reasoning_effort
    )
    provider = await LlmQueryService.get_provider(
        session, LlmTypes.GetProviderCommand(model.provider_id)
    )
    if provider is None:
        raise ValueError("Configured provider is missing.")
    for b in book_links:
        count = sum(t.product_lorebook_id == b.id for t in targets)
        if b.scope == "selected" and count == 0 or (b.scope == "all" and count):
            raise ValueError("Invalid lorebook targets.")
    data = {
        "title": product.title,
        "description": product.description,
        "opening_message": product.opening_message,
        "model": {
            "id": str(model.id),
            "provider_id": str(model.provider_id),
            "provider": provider.name,
            "name": model.model_name,
            "family": model.capabilities.get("model_family"),
            "reasoning_effort": product.reasoning_effort,
        },
        "replacement_policy": product.replacement_policy,
    }
    row = await Repository.create_product_snapshot(session, product_id, data)
    snapshot = PersistenceMapper.product_snapshot_entity_to_info(row)
    chars, books, canonical_chars, canonical_books = ({}, {}, [], [])
    for c in char_links:
        component = await CharacterCommandService.freeze_character(
            session, CharacterTypes.FreezeCharacterCommand(c.character_id, owner_id)
        )
        chars[c.id] = await Repository.add_snapshot_character(
            session, snapshot.id, component.id, c
        )
        canonical_chars.append(
            {
                "source_id": str(c.character_id),
                "data": component.snapshot_data,
                "order": c.role_order,
                "role": c.role_name,
                "primary": c.is_primary,
            }
        )
    source_ids = {c.id: str(c.character_id) for c in char_links}
    for b in book_links:
        book_component = await LorebookCommandService.freeze_lorebook(
            session, LorebookTypes.FreezeLorebookCommand(b.lorebook_id, owner_id)
        )
        books[b.id] = await Repository.add_snapshot_lorebook(
            session, snapshot.id, book_component.id, b
        )
        canonical_books.append(
            {
                "source_id": str(b.lorebook_id),
                "data": book_component.snapshot_data,
                "role": b.role,
                "priority": b.priority,
                "required": b.is_required,
                "scope": b.scope,
                "targets": sorted(
                    source_ids[t.product_character_id]
                    for t in targets
                    if t.product_lorebook_id == b.id
                ),
            }
        )
    for t in targets:
        await Repository.add_snapshot_target(
            session,
            snapshot.id,
            chars[t.product_character_id],
            books[t.product_lorebook_id],
        )
    book_by_source = {b.lorebook_id: b.id for b in book_links}
    for start in starts:
        entry = await LorebookQueryService.get_lorebook_entry(
            session,
            LorebookTypes.GetLorebookEntryCommand(
                lorebook_id=start.lorebook_id, entry_id=start.entry_id
            ),
        )
        await Repository.add_snapshot_start(
            session,
            snapshot.id,
            books[book_by_source[start.lorebook_id]],
            entry,
            start.sort_order,
        )
    canonical = {
        "product": data,
        "characters": canonical_chars,
        "lorebooks": sorted(canonical_books, key=lambda b: str(b["source_id"])),
        "starts": [str(s.entry_id) for s in sorted(starts, key=lambda s: s.sort_order)],
    }
    final_data = {
        **data,
        "content_digest": hashlib.sha256(
            json.dumps(canonical, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest(),
    }
    row = await Repository.finish_product_snapshot(
        session, product_id, snapshot.id, final_data
    )
    return PersistenceMapper.product_snapshot_entity_to_info(row)
