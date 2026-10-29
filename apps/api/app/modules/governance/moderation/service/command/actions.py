"""평가에 근거한 조치 접수·취소. 실제 제재 상태는 변경하지 않는다."""

from typing import cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.idempotency import lock_key
from app.db.transaction import use_case_transaction
from app.modules.content.product import types as ProductTypes
from app.modules.content.product.service import query as ProductQueryService
from app.modules.governance.moderation import types as Types
from app.modules.governance.moderation.mapper import persistence as PersistenceMapper
from app.modules.governance.moderation.repository import review as ReviewRepository
from app.modules.governance.moderation.service.util import (
    validation as ValidationServiceUtil,
)


def _validate_action(command: Types.RequestActionCommand) -> None:
    """현재 지원하는 조치·scope·기간·해제 입력을 검증한다."""
    ValidationServiceUtil.validate_target(command.target_type, command.target_id)
    scopes = {"user": {"login", "publish"}, "product": {"product_access", "publish"}}
    if (
        command.target_type not in scopes
        or command.scope not in scopes[command.target_type]
        or command.action_type not in {"warn", "restrict", "suspend", "ban", "revoke"}
    ):
        raise Types.ModerationError("invalid_input")
    if command.action_type == "ban" and command.target_type != "user":
        raise Types.ModerationError("invalid_input")
    if not isinstance(command.idempotency_key, UUID) or not isinstance(
        command.assessment_id, UUID
    ):
        raise Types.ModerationError("invalid_input")
    ValidationServiceUtil.validate_time(command.starts_at, optional=False)
    ValidationServiceUtil.validate_time(command.ends_at)
    if command.ends_at is not None and command.ends_at <= command.starts_at:
        raise Types.ModerationError("invalid_input")
    if (command.action_type == "revoke") != (command.reverses_action_id is not None):
        raise Types.ModerationError("invalid_input")
    if command.action_type in {"warn", "ban", "revoke"} and command.ends_at is not None:
        raise Types.ModerationError("invalid_input")


async def request_action(
    session: AsyncSession,
    command: Types.RequestActionCommand,
    *,
    actor: Types.ActorCommand,
) -> Types.ActionInfo:
    """관리자가 확정 평가에 근거해 pending 조치를 멱등 기록한다. 적용 성공은 기록하지 않는다."""
    actor_id = actor.user_id
    _validate_action(command)
    async with use_case_transaction(session):
        await ValidationServiceUtil._require_actor(session, actor_id, admin=True)
        await lock_key(session, "moderation.action", str(command.idempotency_key))
        existing_action_entity = await ReviewRepository.get_action_by_key(
            session, command.idempotency_key
        )
        existing = PersistenceMapper.action_entity_to_info(existing_action_entity)
        if existing is not None:
            ValidationServiceUtil.require_match(
                ValidationServiceUtil.request_fingerprint(command),
                ValidationServiceUtil.request_fingerprint(
                    ValidationServiceUtil.action_request_info(existing)
                ),
            )
            return existing
        # 재평가와 조치 요청을 직렬화해 이미 대체된 판단으로 새 제재를 요청하지 않는다.
        assessment_row = await ReviewRepository.get_assessment(
            session, command.assessment_id
        )
        assessment = ValidationServiceUtil.require_info(
            PersistenceMapper.assessment_row_to_info(assessment_row)
        )
        await lock_key(
            session,
            "moderation.target",
            f"{assessment.target_type}:{assessment.target_id}",
        )
        superseding_id_row = await ReviewRepository.get_superseding_assessment(
            session, assessment.id
        )
        if PersistenceMapper.scalar_row_to_value(superseding_id_row) is not None:
            raise Types.ModerationError("state_conflict")
        if command.action_type != "revoke" and assessment.outcome != "violation":
            raise Types.ModerationError("state_conflict")
        if (command.target_type, command.target_id) != (
            assessment.target_type,
            assessment.target_id,
        ):
            if assessment.target_type != "product" or command.target_type != "user":
                raise Types.ModerationError("invalid_link")
            product = await ProductQueryService.get_product_state(
                session,
                ProductTypes.GetProductStateCommand(product_id=assessment.target_id),
            )
            if product is None or product.owner_id != command.target_id:
                raise Types.ModerationError("invalid_link")
        if command.reverses_action_id is not None:
            previous_action_entity = await ReviewRepository.get_action(
                session, command.reverses_action_id, lock=True
            )
            previous = ValidationServiceUtil.require_info(
                PersistenceMapper.action_entity_to_info(previous_action_entity)
            )
            if (
                previous.status != "applied"
                or previous.action_type not in {"restrict", "suspend", "ban"}
                or (previous.target_type, previous.target_id, previous.scope)
                != (command.target_type, command.target_id, command.scope)
            ):
                raise Types.ModerationError("invalid_link")
            reversal_id_row = await ReviewRepository.get_active_reversal_id(
                session, previous.id
            )
            if PersistenceMapper.scalar_row_to_value(reversal_id_row) is not None:
                raise Types.ModerationError("state_conflict")
        created_action_entity = await ReviewRepository.create_action(
            session,
            {
                "assessment_id": command.assessment_id,
                "target_type": command.target_type,
                "target_id": command.target_id,
                "action_type": command.action_type,
                "scope": command.scope,
                "starts_at": command.starts_at,
                "ends_at": command.ends_at,
                "idempotency_key": command.idempotency_key,
                "reverses_action_id": command.reverses_action_id,
                "status": "pending",
            },
        )
        result = PersistenceMapper.action_entity_to_info(created_action_entity)
        await ReviewRepository.create_admin_audit(
            session,
            actor_id,
            "moderation.action.request",
            result.id,
            {"assessment_id": str(result.assessment_id)},
        )
        return result


async def cancel_pending_action(
    session: AsyncSession,
    command: Types.CancelActionCommand,
    *,
    actor: Types.ActorCommand,
) -> Types.ActionInfo:
    """활성 관리자가 pending 조치만 취소하고 동일 취소 재호출은 재사용한다."""
    actor_id = actor.user_id
    async with use_case_transaction(session):
        await ValidationServiceUtil._require_actor(session, actor_id, admin=True)
        action_entity = await ReviewRepository.get_action(
            session, command.action_id, lock=True
        )
        info = ValidationServiceUtil.require_info(
            PersistenceMapper.action_entity_to_info(action_entity)
        )
        if info.status == "cancelled":
            return info
        if info.status != "pending":
            raise Types.ModerationError("state_conflict")
        cancelled_action_entity = await ReviewRepository.cancel_action(session, info.id)
        # 위에서 존재를 확인하고 잠근 동일 ID를 같은 트랜잭션에서 UPDATE RETURNING한다.
        # 삭제 경쟁이 없으므로 mapper 결과는 존재한다. 기존 오류/반환 동작은 유지한다.
        result = cast(
            Types.ActionInfo,
            PersistenceMapper.action_entity_to_info(cancelled_action_entity),
        )
        await ReviewRepository.create_admin_audit(
            session, actor_id, "moderation.action.cancel", result.id, {}
        )
        return result
