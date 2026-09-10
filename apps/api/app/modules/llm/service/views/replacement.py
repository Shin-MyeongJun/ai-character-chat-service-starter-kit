from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.modules.llm import types as Types
from app.modules.llm.service import query as QueryService
from app.modules.llm.service.util.replacement_policy import choose_replacement
from app.modules.llm.types import ModelNoticeView


async def execution_notice(
    session, command: Types.ExecutionNoticeCommand
) -> ModelNoticeView | None:
    """Read-only availability for customers and creators; never expose prompts."""
    snapshot = command.snapshot
    now = command.now
    now = now or datetime.now(UTC)
    configuration = snapshot.snapshot_data["model"]
    model = await QueryService.get_model(
        session, Types.GetModelCommand(UUID(configuration["id"]))
    )
    if model is None:
        return ModelNoticeView(state="paused", reason="model_missing")
    provider = await QueryService.get_provider(
        session, Types.GetProviderCommand(model.provider_id)
    )
    if provider is None:
        return ModelNoticeView(state="paused", reason="model_missing")
    available = (
        model.is_enabled
        and provider.is_enabled
        and (model.shutdown_at is None or now < model.shutdown_at)
    )
    announced = (
        model.retirement_announced_at is not None
        and now >= model.retirement_announced_at
    )
    if available and (not announced):
        return None
    deadline = (
        max(model.retirement_announced_at, model.shutdown_at - timedelta(days=1))
        if announced
        and model.retirement_announced_at is not None
        and model.shutdown_at is not None
        else now
    )
    effective_at = max(now, deadline) if available else now
    policy = snapshot.snapshot_data.get("replacement_policy", {})
    candidates = await QueryService.list_candidate_models(session)
    choice = choose_replacement(
        model, candidates, policy, configuration["reasoning_effort"], now=effective_at
    )
    continuing = available and (
        now < deadline or policy.get("unavailable") == "use_original_until_shutdown"
    )
    return ModelNoticeView(
        state=("scheduled" if now < effective_at else "replacement_ready")
        if choice
        else "replacement_unavailable"
        if continuing
        else "paused",
        model_id=model.id,
        model_name=model.model_name,
        announced_at=model.retirement_announced_at,
        shutdown_at=model.shutdown_at,
        transition_deadline=deadline,
        replacement_model_id=choice[0].id if choice else None,
        replacement_model_name=choice[0].model_name if choice else None,
        replacement_reasoning_effort=choice[1] if choice else None,
        unavailable_policy=policy.get("unavailable", "pause"),
    )
