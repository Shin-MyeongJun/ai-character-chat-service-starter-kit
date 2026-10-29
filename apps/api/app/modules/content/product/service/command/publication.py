# 상위 publish 트랜잭션에서 원본을 잠그고 캐릭터·로어북 복사본과 상품 버전을 만든다.
# content_digest는 콘텐츠/구성 비교용이며 이미지·에셋 변경은 releases의 별도 manifest로 판정한다.
"Internal atomic publication builder; public command adds required release notes."

import hashlib
import json
from typing import TypedDict, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

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


class _CanonicalCharacterData(TypedDict):
    source_id: str
    data: dict[str, CharacterTypes.CharacterSnapshotJsonValue]
    order: int
    role: str | None
    primary: bool


class _CanonicalLorebookData(TypedDict):
    source_id: str
    data: LorebookTypes.LorebookSnapshotData
    role: str
    priority: int
    required: bool
    scope: str
    targets: list[str]


class _CanonicalPublicationData(TypedDict):
    product: Types.ProductSnapshotData
    characters: list[_CanonicalCharacterData]
    lorebooks: list[_CanonicalLorebookData]
    starts: list[str]


async def _build_publication(
    session: AsyncSession, command: Types.BuildPublicationCommand
) -> Types.ProductSnapshotInfo:
    """Caller must own a transaction. Product/source locks serialize all publication reads."""
    product_id = command.product_id
    owner_id = command.owner_id
    if not session.in_transaction():
        raise RuntimeError("Publication requires a caller transaction.")
    product = await QueryService.get_owned_product(
        session,
        Types.OwnedProductCommand(product_id=product_id, owner_id=owner_id, lock=True),
    )
    composition_row = await Repository.get_product_composition(session, product_id)
    composition = PersistenceMapper.product_composition_row_to_state_info(
        composition_row
    )
    character_links, lorebook_links, targets = (
        composition.characters,
        sorted(composition.books, key=lambda lorebook_link: lorebook_link.id),
        composition.targets,
    )
    await CharacterQueryService.get_owned_characters(
        session,
        CharacterTypes.GetOwnedCharactersCommand(
            ids=tuple(
                character_link.character_id for character_link in character_links
            ),
            owner_id=owner_id,
            lock=True,
        ),
    )
    await LorebookQueryService.get_owned_lorebooks(
        session,
        LorebookTypes.GetOwnedLorebooksCommand(
            ids=tuple(lorebook_link.lorebook_id for lorebook_link in lorebook_links),
            owner_id=owner_id,
            lock=True,
        ),
    )
    _, starts = await SettingsCommandService._validate_publication(session, product)
    # _validate_publication above requires both fields while product stays locked.
    assert product.default_model_id is not None and product.reasoning_effort is not None
    model = await SettingsCommandService._validate_model(
        session, product.default_model_id, product.reasoning_effort
    )
    provider = await LlmQueryService.get_provider(
        session, LlmTypes.GetProviderCommand(model.provider_id)
    )
    if provider is None:
        raise ValueError("Configured provider is missing.")
    for lorebook_link in lorebook_links:
        count = sum(
            target.product_lorebook_id == lorebook_link.id for target in targets
        )
        if (
            lorebook_link.scope == "selected"
            and count == 0
            or (lorebook_link.scope == "all" and count)
        ):
            raise ValueError("Invalid lorebook targets.")
    data: Types.ProductSnapshotData = {
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
    created_snapshot_row = await Repository.create_product_snapshot(
        session, product_id, data
    )
    snapshot = PersistenceMapper.product_snapshot_entity_to_info(created_snapshot_row)
    snapshot_character_ids_by_link_id: dict[UUID, UUID] = {}
    snapshot_lorebook_ids_by_link_id: dict[UUID, UUID] = {}
    canonical_characters: list[_CanonicalCharacterData] = []
    canonical_lorebooks: list[_CanonicalLorebookData] = []
    scene_options: Types.ProductJsonObject = {}
    for character_link in character_links:
        character_snapshot = await CharacterCommandService.freeze_character(
            session,
            CharacterTypes.FreezeCharacterCommand(
                character_id=character_link.character_id, owner_id=owner_id
            ),
        )
        snapshot_character_ids_by_link_id[
            character_link.id
        ] = await Repository.add_snapshot_character(
            session, snapshot.id, character_snapshot.id, character_link
        )
        canonical_characters.append(
            {
                "source_id": str(character_link.character_id),
                "data": character_snapshot.snapshot_data,
                "order": character_link.role_order,
                "role": character_link.role_name,
                "primary": character_link.is_primary,
            }
        )
    source_character_ids_by_link_id = {
        character_link.id: str(character_link.character_id)
        for character_link in character_links
    }
    for lorebook_link in lorebook_links:
        lorebook_snapshot = await LorebookCommandService.freeze_lorebook(
            session,
            LorebookTypes.FreezeLorebookCommand(
                lorebook_id=lorebook_link.lorebook_id, owner_id=owner_id
            ),
        )
        snapshot_lorebook_ids_by_link_id[
            lorebook_link.id
        ] = await Repository.add_snapshot_lorebook(
            session, snapshot.id, lorebook_snapshot.id, lorebook_link
        )
        canonical_lorebooks.append(
            {
                "source_id": str(lorebook_link.lorebook_id),
                "data": lorebook_snapshot.snapshot_data,
                "role": lorebook_link.role,
                "priority": lorebook_link.priority,
                "required": lorebook_link.is_required,
                "scope": lorebook_link.scope,
                "targets": sorted(
                    source_character_ids_by_link_id[target.product_character_id]
                    for target in targets
                    if target.product_lorebook_id == lorebook_link.id
                ),
            }
        )
    for target in targets:
        await Repository.add_snapshot_target(
            session,
            snapshot.id,
            snapshot_character_ids_by_link_id[target.product_character_id],
            snapshot_lorebook_ids_by_link_id[target.product_lorebook_id],
        )
    lorebook_link_ids_by_source_id = {
        lorebook_link.lorebook_id: lorebook_link.id for lorebook_link in lorebook_links
    }
    for start in starts:
        start_entry = await LorebookQueryService.get_lorebook_entry(
            session,
            LorebookTypes.GetLorebookEntryCommand(
                lorebook_id=start.lorebook_id, entry_id=start.entry_id
            ),
        )
        # Parent lorebooks remain locked; publication validation found this start.
        assert start_entry is not None, "Validated start entry disappeared."
        await Repository.add_snapshot_start(
            session,
            snapshot.id,
            snapshot_lorebook_ids_by_link_id[
                lorebook_link_ids_by_source_id[start.lorebook_id]
            ],
            start_entry,
            start.sort_order,
        )
        if "studio_scene_v1" in start_entry.metadata:
            # Lorebook metadata came from JSONB. This open scene payload is JSON,
            # although the public metadata type also permits other objects.
            scene_options[str(start_entry.id)] = cast(
                Types.ProductJsonValue, start_entry.metadata["studio_scene_v1"]
            )
    canonical: _CanonicalPublicationData = {
        "product": data,
        "characters": canonical_characters,
        "lorebooks": sorted(
            canonical_lorebooks,
            key=lambda lorebook_link: str(lorebook_link["source_id"]),
        ),
        "starts": [str(s.entry_id) for s in sorted(starts, key=lambda s: s.sort_order)],
    }
    final_data = data.copy()
    if scene_options:
        final_data["studio_start_options"] = scene_options
    final_data["content_digest"] = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    finished_snapshot_row = await Repository.finish_product_snapshot(
        session, product_id, snapshot.id, final_data
    )
    return PersistenceMapper.product_snapshot_entity_to_info(finished_snapshot_row)
