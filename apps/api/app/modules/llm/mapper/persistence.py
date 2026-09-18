# DB 모델의 capabilities를 deepcopy하여 세션 밖에 전달할 Info를 만든다.
from copy import deepcopy
from typing import overload

from app.db.models.model_routing import Model
from app.modules.llm import types as Types


@overload
def model_entity_to_info(entity: Model) -> Types.ModelInfo: ...


@overload
def model_entity_to_info(entity: None) -> None: ...


def model_entity_to_info(entity: Model | None) -> Types.ModelInfo | None:
    if entity is None:
        return None
    return Types.ModelInfo(
        **{
            name: deepcopy(getattr(entity, name))
            for name in Types.ModelInfo.__dataclass_fields__
        }
    )


def provider_entity_to_info(entity) -> Types.ProviderInfo | None:
    if entity is None:
        return None
    return Types.ProviderInfo(entity.id, entity.name, entity.is_enabled)


def models_entities_to_info(entities) -> list[Types.ModelInfo]:
    return [model_entity_to_info(entity) for entity in entities]


def model_replacement_entity_to_exists(entity) -> bool:
    return entity is not None
