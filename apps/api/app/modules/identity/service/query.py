# 상품 관리·모델 종료 공지에서 DB 사용자가 active 상태의 admin인지 검사한다.
# 없거나 권한이 없으면 같은 LookupError를 반환한다. 로그인·토큰 인증 기능은 이 파일에 없다.
from uuid import UUID

from app.modules.identity import repository as Repository
from app.modules.identity import types as Types
from app.modules.identity.mapper import persistence as PersistenceMapper


async def require_admin(session, command: Types.GetUserCommand) -> Types.UserAccessInfo:
    """최신 DB 상태에서 활성 관리자만 허용하고 기존 LookupError 계약을 유지한다."""
    row = await Repository.get_user(session, command.user_id, refresh=True)
    info = PersistenceMapper.user_entity_to_access_info(row)
    if info is None or info.role != "admin" or info.status != "active":
        raise LookupError("Administrative operation unavailable.")
    return info


async def require_active_user(
    session, command: Types.GetUserCommand
) -> Types.UserAccessInfo:
    """인증된 호출자가 전달한 내부 ID의 활성 상태만 재검증한다. 토큰 인증을 대신하지 않는다."""
    row = await Repository.get_user(session, command.user_id, refresh=True)
    info = PersistenceMapper.user_entity_to_access_info(row)
    if info is None or info.status != "active":
        raise LookupError("Active user unavailable.")
    return info


async def get_reportable_user(session, command: Types.GetUserCommand) -> UUID:
    """신고 대상 사용자의 존재만 확인하고 개인정보 없이 내부 ID를 반환한다."""
    row = await Repository.get_user(session, command.user_id, refresh=True)
    info = PersistenceMapper.user_entity_to_access_info(row)
    if info is None:
        raise LookupError("User unavailable.")
    return info.id
