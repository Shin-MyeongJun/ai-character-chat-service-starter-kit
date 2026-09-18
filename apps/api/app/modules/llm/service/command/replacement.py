# 관리자의 모델 종료 공지와 상품 스냅샷별 실행 모델 결정을 담당한다.
# resolve_execution은 현재 후보에서 매번 선택하고 동일 스냅샷·원본·대상 조합의 기록을 중복 생성하지 않는다.
# 기존 기록의 대상을 고정해서 재사용하는 방식은 아니며, 외부 모델 호출은 하지 않는다.
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.db.transaction import use_case_transaction
from app.modules.content.product import types as ProductTypes
from app.modules.content.product.service import query as ProductQueryService
from app.modules.identity import types as IdentityTypes
from app.modules.identity.service import query as IdentityQueryService
from app.modules.llm import repository as Repository
from app.modules.llm import types as Types
from app.modules.llm.mapper import persistence as PersistenceMapper
from app.modules.llm.service import query as QueryService
from app.modules.llm.service.util.replacement_policy import choose_replacement
from app.modules.llm.types import ExecutionView


async def announce_retirement(
    session, command: Types.AnnounceRetirementCommand
) -> Types.ModelInfo:
    actor_id = command.actor_id
    model_id = command.model_id
    announced_at = command.announced_at
    shutdown_at = command.shutdown_at
    for instant in (announced_at, shutdown_at):
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError("Retirement dates require timezones.")
    if shutdown_at <= announced_at:
        raise ValueError("Shutdown must follow announcement.")
    async with use_case_transaction(session):
        await IdentityQueryService.require_admin(
            session, IdentityTypes.GetUserCommand(actor_id)
        )
        row = await Repository.set_model_retirement(
            session, model_id, announced_at, shutdown_at
        )
        model = PersistenceMapper.model_entity_to_info(row)
        if model is None:
            raise LookupError("Model not found.")
        return model


# 현재 가용성과 허용 후보로 실행 설정을 결정한다. 대체 기록은 같은 대상 조합의 중복 삽입만 피한다.
# 기존 기록이 있어도 후보를 다시 선택하므로 설정 변경 후에도 같은 대상이라는 보장은 없다.
async def resolve_execution(
    session, command: Types.ResolveExecutionCommand
) -> ExecutionView:
    """Caller transaction; locks version to make replacement selection idempotent.

    Can run at announcement time to prepare a plan, and on every generation. An
    external job may call this for affected versions; alarm delivery is separate.
    """
    async with use_case_transaction(session):
        snapshot_id = command.snapshot_id
        now = command.now
        now = now or datetime.now(UTC)
        snapshot = await ProductQueryService.get_product_snapshot(
            session, ProductTypes.ProductSnapshotCommand(snapshot_id, lock=True)
        )
        if snapshot is None:
            raise LookupError("Version not found.")
        configuration = snapshot.snapshot_data["model"]
        model = await QueryService.get_model(
            session, Types.GetModelCommand(UUID(configuration["id"]))
        )
        if model is None:
            raise ValueError("Configured model is missing.")
        provider = await QueryService.get_provider(
            session, Types.GetProviderCommand(model.provider_id)
        )
        effort = configuration["reasoning_effort"]
        if provider is None:
            raise ValueError("Configured provider is missing.")
        original_available = (
            model.is_enabled
            and provider.is_enabled
            and (model.shutdown_at is None or now < model.shutdown_at)
        )
        announced = (
            model.retirement_announced_at is not None
            and now >= model.retirement_announced_at
        )
        if not announced and original_available:
            return ExecutionView(
                model_id=model.id,
                provider=provider.name,
                model=model.model_name,
                reasoning_effort=effort,
                replacement=False,
                scheduled_at=None,
            )
        deadline = (
            max(model.retirement_announced_at, model.shutdown_at - timedelta(days=1))
            if announced
            and model.retirement_announced_at is not None
            and model.shutdown_at is not None
            else now
        )
        effective_at = max(now, deadline) if original_available else now
        candidates = await QueryService.list_candidate_models(session)
        choice = choose_replacement(
            model,
            candidates,
            snapshot.snapshot_data.get("replacement_policy", {}),
            effort,
            now=effective_at,
        )
        if choice is None:
            if original_available and (
                now < deadline
                or snapshot.snapshot_data.get("replacement_policy", {}).get(
                    "unavailable"
                )
                == "use_original_until_shutdown"
            ):
                return ExecutionView(
                    model_id=model.id,
                    provider=provider.name,
                    model=model.model_name,
                    reasoning_effort=effort,
                    replacement=False,
                    scheduled_at=deadline,
                    replacement_unavailable=True,
                )
            raise ValueError(
                "No permitted replacement available; generation paused, history retained."
            )
        target, target_effort = choice
        row = await Repository.get_model_replacement(
            session, snapshot_id, model.id, target.id
        )
        exists = PersistenceMapper.model_replacement_entity_to_exists(row)
        if not exists:
            await Repository.create_model_replacement(
                session, snapshot_id, model.id, target.id, target_effort, effective_at
            )
        if now < effective_at:
            return ExecutionView(
                model_id=model.id,
                provider=provider.name,
                model=model.model_name,
                reasoning_effort=effort,
                replacement=False,
                scheduled_at=effective_at,
                planned_model_id=target.id,
            )
        target_provider = await QueryService.get_provider(
            session, Types.GetProviderCommand(target.provider_id)
        )
        if target_provider is None:
            raise ValueError("Replacement provider is missing.")
        return ExecutionView(
            model_id=target.id,
            provider=target_provider.name,
            model=target.model_name,
            reasoning_effort=target_effort,
            replacement=True,
            scheduled_at=effective_at,
        )
