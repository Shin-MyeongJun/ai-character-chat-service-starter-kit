from dataclasses import dataclass
from typing import Literal
from uuid import UUID
from sqlalchemy import delete, select
from app.db.models.product import ProductStartSet, ProductCharacter, ProductLorebook
from app.db.models.lorebook import LorebookEntry
from app.db.models.model_routing import Model, Provider
from app.modules.content.product import repository


@dataclass(frozen=True, slots=True)
class Settings:
    model_id: UUID
    reasoning_effort: str
    start_entry_ids: tuple[UUID, ...]
    replacement_scope: Literal['same_family', 'same_provider', 'allowlist'] = 'same_family'
    replacement_model_ids: tuple[UUID, ...] = ()
    unavailable_policy: Literal['pause', 'use_original_until_shutdown'] = 'pause'


async def validate_model(session, model_id, effort):
    model = await session.scalar(select(Model).join(Provider).where(Model.id == model_id, Model.is_enabled.is_(True), Provider.is_enabled.is_(True)))
    if model is None:
        raise ValueError('Model is unavailable.')
    efforts = model.capabilities.get('reasoning_efforts', [])
    if effort not in efforts:
        raise ValueError('Model does not support this reasoning effort.')
    return model


async def set_settings(session, *, product_id, owner_id, value: Settings):
    if value.replacement_scope not in ('same_family','same_provider','allowlist') or value.unavailable_policy not in ('pause','use_original_until_shutdown'):
        raise ValueError('Invalid replacement policy.')
    if not 1 <= len(value.start_entry_ids) <= 100 or len(set(value.start_entry_ids)) != len(value.start_entry_ids):
        raise ValueError('Select 1–100 distinct start options.')
    if len(value.replacement_model_ids) > 100 or len(set(value.replacement_model_ids)) != len(value.replacement_model_ids):
        raise ValueError('Invalid replacement allowlist.')
    if value.replacement_scope == 'allowlist' and not value.replacement_model_ids:
        raise ValueError('Allowlist requires at least one model.')
    async with session.begin():
        product = await repository.owned(session, product_id, owner_id, lock=True)
        await validate_model(session, value.model_id, value.reasoning_effort)
        if value.replacement_model_ids:
            found = list(await session.scalars(select(Model.id).where(Model.id.in_(value.replacement_model_ids))))
            if len(found) != len(value.replacement_model_ids):
                raise ValueError('Unknown replacement model.')
        entries = list(await session.scalars(select(LorebookEntry).join(ProductLorebook, ProductLorebook.lorebook_id == LorebookEntry.lorebook_id).where(ProductLorebook.product_id == product_id, LorebookEntry.id.in_(value.start_entry_ids), LorebookEntry.entry_type == 'start_set', LorebookEntry.is_enabled.is_(True))))
        if len(entries) != len(value.start_entry_ids):
            raise ValueError('Start options must be enabled start_set entries in this product.')
        product.default_model_id = value.model_id
        product.reasoning_effort = value.reasoning_effort
        product.replacement_policy = {'scope': value.replacement_scope, 'model_ids': [str(i) for i in value.replacement_model_ids], 'unavailable': value.unavailable_policy}
        await session.execute(delete(ProductStartSet).where(ProductStartSet.product_id == product_id))
        by_id = {e.id: e for e in entries}
        for order, entry_id in enumerate(value.start_entry_ids):
            session.add(ProductStartSet(product_id=product_id, lorebook_id=by_id[entry_id].lorebook_id, entry_id=entry_id, sort_order=order))
        await session.flush()
        return value


async def validate_publication(session, product):
    if not product.title.strip() or not product.opening_message or not product.opening_message.strip():
        raise ValueError('Title and opening message are required.')
    chars = list(await session.scalars(select(ProductCharacter).where(ProductCharacter.product_id == product.id)))
    if not chars or sum(c.is_primary for c in chars) != 1:
        raise ValueError('Publication requires characters and exactly one primary.')
    if not product.default_model_id or product.reasoning_effort is None:
        raise ValueError('Model and reasoning settings are required.')
    await validate_model(session, product.default_model_id, product.reasoning_effort)
    starts = list(await session.scalars(select(ProductStartSet).where(ProductStartSet.product_id == product.id)))
    if not starts:
        raise ValueError('At least one start option is required.')
    valid = list(await session.scalars(select(LorebookEntry.id).where(LorebookEntry.id.in_([s.entry_id for s in starts]), LorebookEntry.entry_type == 'start_set', LorebookEntry.is_enabled.is_(True))))
    if len(valid) != len(starts):
        raise ValueError('Start options changed; configure them again.')
    return chars, starts
