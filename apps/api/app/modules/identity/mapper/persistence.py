"""이미 조회한 Entity/스칼라를 값으로 바꾼다. 조회·현재 시각·정책 판단은 하지 않는다."""

from app.modules.identity import types as Types


def user_entity_to_access_info(entity) -> Types.UserAccessInfo | None:
    if entity is None:
        return None
    return Types.UserAccessInfo(entity.id, entity.role, entity.status)


def user_entity_to_credential_info(entity) -> Types.CredentialInfo | None:
    if entity is None:
        return None
    return Types.CredentialInfo(
        Types.UserInfo(entity.id, entity.email, entity.email_verified),
        entity.password_hash,
        entity.status,
        entity.pending_expires_at,
    )


def session_entity_to_info(entity) -> Types.SessionInfo | None:
    if entity is None:
        return None
    return Types.SessionInfo(
        entity.id,
        entity.user_id,
        entity.refresh_hash,
        entity.expires_at,
        entity.revoked_at,
    )


def action_entity_to_info(entity) -> Types.ActionTokenInfo | None:
    if entity is None:
        return None
    return Types.ActionTokenInfo(
        entity.id, entity.user_id, entity.purpose, entity.expires_at, entity.consumed_at
    )


def scalar_row_to_used(value) -> bool:
    return value is not None


def cleanup_row_to_info(value) -> Types.CleanupInfo:
    return Types.CleanupInfo(*value)
