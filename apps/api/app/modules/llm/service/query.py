# DB에 등록된 모델·provider의 활성 여부와 종료 시각, reasoning_effort를 검증한다.
# SDK 어댑터의 실제 지원 목록과는 별도 검증이므로 등록만으로 외부 호출 성공을 보장하지 않는다.
from datetime import UTC, datetime
from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.llm import repository as Repository
from app.modules.llm import types as Types
from app.modules.llm.mapper import persistence as PersistenceMapper


async def get_model(
    session: AsyncSession, command: Types.GetModelCommand
) -> Types.ModelInfo | None:
    entity = await Repository.get_model(session, command.model_id)
    return PersistenceMapper.model_entity_to_info(entity)


async def get_provider(
    session: AsyncSession, command: Types.GetProviderCommand
) -> Types.ProviderInfo | None:
    entity = await Repository.get_provider(session, command.provider_id)
    return PersistenceMapper.provider_entity_to_info(entity)


async def list_candidate_models(session: AsyncSession) -> list[Types.ModelInfo]:
    entities = await Repository.list_candidate_models(session)
    return PersistenceMapper.models_entities_to_info(entities)


async def validate_model(
    session: AsyncSession, command: Types.ValidateModelCommand
) -> Types.ModelInfo:
    model = await get_model(session, Types.GetModelCommand(model_id=command.model_id))
    if model is None:
        raise ValueError("Model is unavailable.")
    provider = await get_provider(
        session, Types.GetProviderCommand(provider_id=model.provider_id)
    )
    if (
        not model.is_enabled
        or provider is None
        or not provider.is_enabled
        or (model.shutdown_at is not None and model.shutdown_at <= datetime.now(UTC))
    ):
        raise ValueError("Model is unavailable.")
    # The catalog's known effort field is read without closing its extension map.
    capabilities = cast(Types.ModelCapabilities, model.capabilities)
    if command.reasoning_effort not in capabilities.get("reasoning_efforts", []):
        raise ValueError("Model does not support this reasoning effort.")
    return model
