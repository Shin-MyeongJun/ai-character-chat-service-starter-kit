# 상품 관리·모델 종료 공지에서 DB 사용자가 active 상태의 admin인지 검사한다.
# 없거나 권한이 없으면 같은 LookupError를 반환한다. 로그인·토큰 인증 기능은 이 파일에 없다.
from app.modules.identity import repository as Repository
from app.modules.identity import types as Types
from app.modules.identity.mapper import persistence as PersistenceMapper


async def require_admin(session, command: Types.GetUserCommand) -> Types.UserAccessInfo:
    row = await Repository.get_user(session, command.user_id)
    info = PersistenceMapper.user_entity_to_access_info(row)
    if info is None or info.role != "admin" or info.status != "active":
        raise LookupError("Administrative operation unavailable.")
    return info
