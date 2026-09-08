from datetime import UTC, datetime, timedelta
from uuid import UUID
from sqlalchemy import select
from app.db.models.model_routing import Model, Provider, ModelReplacement
from app.db.models.snapshot.product import ProductSnapshot
from app.modules.governance.admin.product_policy import require_admin

EFFORTS=('none','minimal','low','medium','high','xhigh','max')


def closest_effort(requested, supported):
    allowed=[e for e in supported if e in EFFORTS]
    if requested not in EFFORTS or not allowed:
        return None
    return min(allowed,key=lambda e:(abs(EFFORTS.index(e)-EFFORTS.index(requested)), EFFORTS.index(e)))


def choose_replacement(original, candidates, policy, effort, *, now):
    scope=policy.get('scope','same_family')
    family=original.capabilities.get('model_family')
    choices=[]
    for model in candidates:
        if model.id==original.id or not model.is_enabled or (model.shutdown_at and model.shutdown_at<=now):
            continue
        same_provider=model.provider_id==original.provider_id
        same_family=bool(family) and same_provider and model.capabilities.get('model_family')==family
        allowed=(scope=='same_family' and same_family) or (scope=='same_provider' and same_provider) or (scope=='allowlist' and str(model.id) in policy.get('model_ids',[]))
        replacement_effort=closest_effort(effort,model.capabilities.get('reasoning_efforts',[]))
        if not allowed or replacement_effort is None:
            continue
        choices.append((not same_family, not same_provider, abs(EFFORTS.index(effort)-EFFORTS.index(replacement_effort)), str(model.id),model,replacement_effort))
    if not choices:
        return None
    best=min(choices,key=lambda x:x[:4])
    return best[4],best[5]


async def announce_retirement(session, *, actor_id, model_id, announced_at, shutdown_at):
    for instant in (announced_at,shutdown_at):
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError('Retirement dates require timezones.')
    if shutdown_at<=announced_at:
        raise ValueError('Shutdown must follow announcement.')
    async with session.begin():
        await require_admin(session,actor_id)
        model=await session.get(Model,model_id,with_for_update=True)
        if model is None:
            raise LookupError('Model not found.')
        model.retirement_announced_at=announced_at
        model.shutdown_at=shutdown_at
        await session.flush()


async def resolve_execution(session, *, snapshot_id, now=None):
    """Caller transaction; locks version to make replacement selection idempotent.

Can run at announcement time to prepare a plan, and on every generation. An
external job may call this for affected versions; alarm delivery is separate.
"""
    now=now or datetime.now(UTC)
    snapshot=await session.get(ProductSnapshot,snapshot_id,with_for_update=True)
    if snapshot is None:
        raise LookupError('Version not found.')
    configuration=snapshot.snapshot_data['model']
    model=await session.get(Model,UUID(configuration['id']))
    if model is None:
        raise ValueError('Configured model is missing.')
    provider=await session.get(Provider,model.provider_id)
    effort=configuration['reasoning_effort']
    original_available=model.is_enabled and provider.is_enabled and (model.shutdown_at is None or now<model.shutdown_at)
    announced=model.retirement_announced_at is not None and now>=model.retirement_announced_at
    if not announced and original_available:
        return {'model_id':model.id,'provider':provider.name,'model':model.model_name,'reasoning_effort':effort,'replacement':False,'scheduled_at':None}
    deadline=max(model.retirement_announced_at,model.shutdown_at-timedelta(days=1)) if announced and model.shutdown_at else now
    effective_at=max(now,deadline) if original_available else now
    candidates=list(await session.scalars(select(Model).join(Provider).where(Provider.is_enabled.is_(True))))
    choice=choose_replacement(model,candidates,snapshot.snapshot_data.get('replacement_policy',{}),effort,now=effective_at)
    if choice is None:
        if original_available and (now<deadline or snapshot.snapshot_data.get('replacement_policy',{}).get('unavailable')=='use_original_until_shutdown'):
            return {'model_id':model.id,'provider':provider.name,'model':model.model_name,'reasoning_effort':effort,'replacement':False,'scheduled_at':deadline,'replacement_unavailable':True}
        raise ValueError('No permitted replacement available; generation paused, history retained.')
    target,target_effort=choice
    existing=await session.scalar(select(ModelReplacement).where(ModelReplacement.product_snapshot_id==snapshot_id,ModelReplacement.from_model_id==model.id,ModelReplacement.to_model_id==target.id))
    if existing is None:
        session.add(ModelReplacement(product_snapshot_id=snapshot_id,from_model_id=model.id,to_model_id=target.id,reasoning_effort=target_effort,effective_at=effective_at))
        await session.flush()
    if now<effective_at:
        return {'model_id':model.id,'provider':provider.name,'model':model.model_name,'reasoning_effort':effort,'replacement':False,'scheduled_at':effective_at,'planned_model_id':target.id}
    target_provider=await session.get(Provider,target.provider_id)
    return {'model_id':target.id,'provider':target_provider.name,'model':target.model_name,'reasoning_effort':target_effort,'replacement':True,'scheduled_at':effective_at}
