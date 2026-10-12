"""관리자 평가 단건과 대상별 이력 조회."""

from app.modules.governance.moderation import types as Types
from app.modules.governance.moderation.mapper import persistence as PersistenceMapper
from app.modules.governance.moderation.repository import review as ReviewRepository
from app.modules.governance.moderation.service.util import (
    validation as ValidationServiceUtil,
)


async def get_assessment(
    session, command: Types.GetAssessmentCommand, *, actor: Types.ActorCommand
) -> Types.AssessmentInfo:
    """활성 관리자에게 평가 결과와 근거 신고 연결을 반환한다."""
    actor_id = actor.user_id
    await ValidationServiceUtil._require_actor(session, actor_id, admin=True)
    row = await ReviewRepository.get_assessment(session, command.assessment_id)
    return ValidationServiceUtil.require_info(
        PersistenceMapper.assessment_row_to_info(row)
    )


async def list_assessments(
    session, command: Types.ListAssessmentsCommand, *, actor: Types.ActorCommand
) -> Types.PageInfo[Types.AssessmentInfo]:
    """관리자가 대상별 평가를 시각·ID 커서로 조회한다."""
    actor_id = actor.user_id
    ValidationServiceUtil.validate_page(command)
    await ValidationServiceUtil._require_actor(session, actor_id, admin=True)
    row = await ReviewRepository.list_assessments(session, command)
    return PersistenceMapper.assessments_row_to_page(row)
