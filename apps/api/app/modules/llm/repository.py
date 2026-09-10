from sqlalchemy import select

from app.db.models.model_routing import Model, ModelReplacement, Provider


async def get_model(session, model_id):
    return await session.get(Model, model_id)


async def get_provider(session, provider_id):
    return await session.get(Provider, provider_id)


async def list_candidate_models(session):
    return list(
        await session.scalars(
            select(Model).join(Provider).where(Provider.is_enabled.is_(True))
        )
    )


async def get_model_replacement(session, snapshot_id, from_id, to_id):
    return await session.scalar(
        select(ModelReplacement).where(
            ModelReplacement.product_snapshot_id == snapshot_id,
            ModelReplacement.from_model_id == from_id,
            ModelReplacement.to_model_id == to_id,
        )
    )


async def create_model_replacement(
    session, snapshot_id, from_id, to_id, effort, effective_at
):
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


async def set_model_retirement(session, model_id, announced_at, shutdown_at):
    model = await session.get(Model, model_id, with_for_update=True)
    if model is None:
        return None
    model.retirement_announced_at, model.shutdown_at = announced_at, shutdown_at
    await session.flush()
    return model
