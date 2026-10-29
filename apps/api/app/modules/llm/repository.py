# 모델 설정과 대체 이력만 저장한다. 후보 조회는 활성 provider만 제한하고 모델 자체 필터는 service가 적용한다.
# 종료 공지 변경은 모델 행을 잠그며, 대체 이력 조회에는 별도 행 잠금이 없다.
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.model_routing import Model, ModelReplacement, Provider


async def get_model(session: AsyncSession, model_id: UUID) -> Model | None:
    return await session.get(Model, model_id)


async def get_provider(session: AsyncSession, provider_id: UUID) -> Provider | None:
    return await session.get(Provider, provider_id)


async def list_candidate_models(session: AsyncSession) -> list[Model]:
    return list(
        await session.scalars(
            select(Model).join(Provider).where(Provider.is_enabled.is_(True))
        )
    )


async def get_model_replacement(
    session: AsyncSession, snapshot_id: UUID, from_id: UUID, to_id: UUID
) -> ModelReplacement | None:
    result = await session.execute(
        select(ModelReplacement).where(
            ModelReplacement.product_snapshot_id == snapshot_id,
            ModelReplacement.from_model_id == from_id,
            ModelReplacement.to_model_id == to_id,
        )
    )
    return result.scalar()


async def create_model_replacement(
    session: AsyncSession,
    snapshot_id: UUID,
    from_id: UUID,
    to_id: UUID,
    effort: str,
    effective_at: datetime,
) -> None:
    session.add(
        ModelReplacement(
            product_snapshot_id=snapshot_id,
            from_model_id=from_id,
            to_model_id=to_id,
            reasoning_effort=effort,
            effective_at=effective_at,
        )
    )
    await session.flush()


async def set_model_retirement(
    session: AsyncSession,
    model_id: UUID,
    announced_at: datetime,
    shutdown_at: datetime,
) -> Model | None:
    model = await session.get(Model, model_id, with_for_update=True)
    if model is None:
        return None
    model.retirement_announced_at, model.shutdown_at = announced_at, shutdown_at
    await session.flush()
    return model
