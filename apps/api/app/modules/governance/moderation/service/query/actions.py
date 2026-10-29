"""관리자 조치 요청·결과·재시도 목록 조회."""

from dataclasses import replace

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.governance.moderation import types as Types
from app.modules.governance.moderation.mapper import persistence as PersistenceMapper
from app.modules.governance.moderation.repository import review as ReviewRepository
from app.modules.governance.moderation.service.util import (
    validation as ValidationServiceUtil,
)


async def get_action(
    session: AsyncSession,
    command: Types.GetActionCommand,
    *,
    actor: Types.ActorCommand,
) -> Types.ActionInfo:
    """활성 관리자가 조치 단건의 현재 적용 상태를 조회한다."""
    actor_id = actor.user_id
    await ValidationServiceUtil._require_actor(session, actor_id, admin=True)
    row = await ReviewRepository.get_action(session, command.action_id)
    return ValidationServiceUtil.require_info(
        PersistenceMapper.action_entity_to_info(row)
    )


async def list_actions(
    session: AsyncSession,
    command: Types.ListActionsCommand,
    *,
    actor: Types.ActorCommand,
) -> Types.PageInfo[Types.ActionInfo]:
    """관리자가 평가·대상·상태별 조치를 커서 조회한다."""
    actor_id = actor.user_id
    ValidationServiceUtil.validate_page(command)
    if any(
        status not in {"pending", "applied", "failed", "cancelled"}
        for status in command.statuses
    ):
        raise Types.ModerationError("invalid_input")
    await ValidationServiceUtil._require_actor(session, actor_id, admin=True)
    row = await ReviewRepository.list_actions(session, command)
    return PersistenceMapper.actions_row_to_page(row)


async def list_retry_actions(
    session: AsyncSession,
    command: Types.ListActionsCommand,
    *,
    actor: Types.ActorCommand,
) -> Types.PageInfo[Types.ActionInfo]:
    """pending/failed 요청만 조회하며 적용이나 상태 변경은 수행하지 않는다."""
    return await list_actions(
        session, replace(command, statuses=("pending", "failed")), actor=actor
    )
