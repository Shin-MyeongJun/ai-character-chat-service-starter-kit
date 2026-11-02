"""이미 조회한 Entity/스칼라를 값으로 바꾼다. 조회·현재 시각·정책 판단은 하지 않는다."""

from typing import overload
from uuid import UUID

from app.db.models.identity import AuthActionToken, AuthMailOutbox, AuthSession, User
from app.modules.identity import repository as Repository
from app.modules.identity import types as Types


@overload
def user_entity_to_access_info(entity: User) -> Types.UserAccessInfo: ...


@overload
def user_entity_to_access_info(entity: None) -> None: ...


def user_entity_to_access_info(entity: User | None) -> Types.UserAccessInfo | None:
    if entity is None:
        return None
    return Types.UserAccessInfo(id=entity.id, role=entity.role, status=entity.status)


@overload
def user_entity_to_credential_info(entity: User) -> Types.CredentialInfo: ...


@overload
def user_entity_to_credential_info(entity: None) -> None: ...


def user_entity_to_credential_info(entity: User | None) -> Types.CredentialInfo | None:
    if entity is None:
        return None
    return Types.CredentialInfo(
        user=Types.UserInfo(
            id=entity.id, email=entity.email, email_verified=entity.email_verified
        ),
        password_hash=entity.password_hash,
        status=entity.status,
        pending_expires_at=entity.pending_expires_at,
    )


@overload
def session_entity_to_info(entity: AuthSession) -> Types.SessionInfo: ...


@overload
def session_entity_to_info(entity: None) -> None: ...


def session_entity_to_info(entity: AuthSession | None) -> Types.SessionInfo | None:
    if entity is None:
        return None
    return Types.SessionInfo(
        id=entity.id,
        user_id=entity.user_id,
        refresh_hash=entity.refresh_hash,
        expires_at=entity.expires_at,
        revoked_at=entity.revoked_at,
    )


def authenticated_session_row_to_infos(
    row: Repository.AuthenticatedSessionRow | None,
) -> tuple[Types.CredentialInfo, Types.SessionInfo] | None:
    if row is None:
        return None
    return user_entity_to_credential_info(row.user), session_entity_to_info(row.session)


@overload
def action_entity_to_info(entity: AuthActionToken) -> Types.ActionTokenInfo: ...


@overload
def action_entity_to_info(entity: None) -> None: ...


def action_entity_to_info(
    entity: AuthActionToken | None,
) -> Types.ActionTokenInfo | None:
    if entity is None:
        return None
    return Types.ActionTokenInfo(
        id=entity.id,
        user_id=entity.user_id,
        purpose=entity.purpose,
        expires_at=entity.expires_at,
        consumed_at=entity.consumed_at,
    )


def scalar_row_to_used(value: UUID | str | int | None) -> bool:
    return value is not None


def cleanup_row_to_info(value: Repository.CleanupRow) -> Types.CleanupInfo:
    return Types.CleanupInfo(*value)


def mail_outbox_entity_to_info(
    entity: AuthMailOutbox | None,
) -> Types.MailOutboxInfo | None:
    if entity is None:
        return None
    return Types.MailOutboxInfo(
        id=entity.id,
        token_hash=entity.token_hash,
        encrypted_token=entity.encrypted_token,
        status=entity.status,
        attempt_count=entity.attempt_count,
        available_at=entity.available_at,
        claim_token=entity.claim_token,
        lease_until=entity.lease_until,
    )
