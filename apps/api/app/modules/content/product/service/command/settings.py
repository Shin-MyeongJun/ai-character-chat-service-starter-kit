# 실행 모델·reasoning effort·시작 원본 항목·대체 정책을 초안에 저장한다.
# 시작 항목은 구성에 포함된 로어북의 enabled start_set이어야 한다. 발행 직전에도 별도 재검증한다.
from app.db.transaction import use_case_transaction
from app.modules.content.lorebook import types as LorebookTypes
from app.modules.content.lorebook.service import query as LorebookQueryService
from app.modules.content.product import repository as Repository
from app.modules.content.product import types as Types
from app.modules.content.product.mapper import persistence as PersistenceMapper
from app.modules.content.product.service import query as QueryService
from app.modules.content.product.service.command import (
    composition as CompositionCommandService,
)
from app.modules.content.product.types import ProductSettingsInfo
from app.modules.llm import types as LlmTypes
from app.modules.llm.service import query as LlmQueryService


async def _validate_model(session, model_id, effort):
    return await LlmQueryService.validate_model(
        session, LlmTypes.ValidateModelCommand(model_id, effort)
    )


# 선택 모델·effort와 연결 로어의 시작 항목, 대체 허용 정책을 확인해 초안 설정을 저장한다.
async def set_settings(
    session, command: Types.SetSettingsCommand
) -> ProductSettingsInfo:
    product_id = command.product_id
    owner_id = command.owner_id
    value = command.value
    if value.replacement_scope not in (
        "same_family",
        "same_provider",
        "allowlist",
    ) or value.unavailable_policy not in ("pause", "use_original_until_shutdown"):
        raise ValueError("Invalid replacement policy.")
    if not 1 <= len(value.start_entry_ids) <= 100 or len(
        set(value.start_entry_ids)
    ) != len(value.start_entry_ids):
        raise ValueError("Select 1–100 distinct start options.")
    if len(value.replacement_model_ids) > 100 or len(
        set(value.replacement_model_ids)
    ) != len(value.replacement_model_ids):
        raise ValueError("Invalid replacement allowlist.")
    if value.replacement_scope == "allowlist" and (not value.replacement_model_ids):
        raise ValueError("Allowlist requires at least one model.")
    async with use_case_transaction(session):
        await QueryService.get_owned_product(
            session, Types.OwnedProductCommand(product_id, owner_id, lock=True)
        )
        await _validate_model(session, value.model_id, value.reasoning_effort)
        for model_id in value.replacement_model_ids:
            if (
                await LlmQueryService.get_model(
                    session, LlmTypes.GetModelCommand(model_id)
                )
                is None
            ):
                raise ValueError("Unknown replacement model.")
        composition = await CompositionCommandService.get_composition(
            session,
            Types.GetCompositionCommand(product_id=product_id, owner_id=owner_id),
        )
        entries = await LorebookQueryService.get_start_entries(
            session,
            LorebookTypes.GetStartEntriesCommand(
                value.start_entry_ids,
                tuple(b.lorebook_id for b in composition.lorebooks),
            ),
        )
        if len(entries) != len(value.start_entry_ids):
            raise ValueError(
                "Start options must be enabled start_set entries in this product."
            )
        await Repository.set_product_settings(session, product_id, value, entries)
        return value


async def _validate_publication(session, product):
    if (
        not product.title.strip()
        or not product.opening_message
        or (not product.opening_message.strip())
    ):
        raise ValueError("Title and opening message are required.")
    row = await Repository.get_product_composition(session, product.id)
    composition = PersistenceMapper.product_composition_row_to_info(row)
    chars = composition.characters
    if not chars or sum(c.is_primary for c in chars) != 1:
        raise ValueError("Publication requires characters and exactly one primary.")
    if not product.default_model_id or product.reasoning_effort is None:
        raise ValueError("Model and reasoning settings are required.")
    await _validate_model(session, product.default_model_id, product.reasoning_effort)
    rows = await Repository.list_product_start_sets(session, product.id)
    starts = PersistenceMapper.product_start_sets_entities_to_info(rows)
    if not starts:
        raise ValueError("At least one start option is required.")
    valid = await LorebookQueryService.get_start_entries(
        session, LorebookTypes.GetStartEntriesCommand(tuple(s.entry_id for s in starts))
    )
    if len(valid) != len(starts):
        raise ValueError("Start options changed; configure them again.")
    return (chars, starts)
