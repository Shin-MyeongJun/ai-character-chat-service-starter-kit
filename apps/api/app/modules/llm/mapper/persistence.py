# DB 모델의 capabilities를 deepcopy하여 세션 밖에 전달할 Info를 만든다.
from collections.abc import Iterable
from copy import deepcopy
from typing import overload

from app.db.models.model_routing import Model, ModelReplacement, Provider
from app.modules.llm import types as Types


@overload
def model_entity_to_info(entity: Model) -> Types.ModelInfo: ...


@overload
def model_entity_to_info(entity: None) -> None: ...


def model_entity_to_info(entity: Model | None) -> Types.ModelInfo | None:
    if entity is None:
        return None
    return Types.ModelInfo(
        id=entity.id,
        provider_id=entity.provider_id,
        model_name=entity.model_name,
        is_enabled=entity.is_enabled,
        capabilities=deepcopy(entity.capabilities),
        retirement_announced_at=entity.retirement_announced_at,
        shutdown_at=entity.shutdown_at,
        context_window=entity.context_window,
    )


@overload
def provider_entity_to_info(entity: Provider) -> Types.ProviderInfo: ...


@overload
def provider_entity_to_info(entity: None) -> None: ...


def provider_entity_to_info(entity: Provider | None) -> Types.ProviderInfo | None:
    if entity is None:
        return None
    return Types.ProviderInfo(entity.id, entity.name, entity.is_enabled)


def models_entities_to_info(entities: Iterable[Model]) -> list[Types.ModelInfo]:
    return [model_entity_to_info(entity) for entity in entities]


def model_replacement_entity_to_exists(entity: ModelReplacement | None) -> bool:
    return entity is not None
