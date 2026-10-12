"""업무 입력 검증·인가·멱등 비교의 내부 보조 함수."""

import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from app.modules.governance.moderation import types as Types
from app.modules.identity import types as IdentityTypes
from app.modules.identity.service import query as IdentityQueryService

TARGETS = {"user", "product", "character", "message"}


async def _require_actor(session, actor_id: UUID, *, admin=False) -> None:
    """인증 경계가 전달한 ID의 활성 상태와 관리자 역할을 DB에서 재검증한다."""
    if not isinstance(actor_id, UUID):
        raise Types.ModerationError("forbidden")
    try:
        if admin:
            await IdentityQueryService.require_admin(
                session, IdentityTypes.GetUserCommand(actor_id)
            )
        else:
            await IdentityQueryService.require_active_user(
                session, IdentityTypes.GetUserCommand(actor_id)
            )
    except LookupError as exc:
        raise Types.ModerationError("forbidden") from exc


def validate_text(value, *, maximum=4000) -> None:
    """비어 있거나 길이 제한을 넘는 텍스트를 거절한다."""
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise Types.ModerationError("invalid_input")


def validate_time(value, *, optional=True) -> None:
    """제공된 시각이 timezone-aware datetime인지 검사한다."""
    if value is None and optional:
        return
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise Types.ModerationError("invalid_input")


def validate_target(target_type, target_id) -> None:
    """지원 대상 종류와 UUID 식별자를 검증한다."""
    if target_type not in TARGETS or not isinstance(target_id, UUID):
        raise Types.ModerationError("invalid_input")


def validate_page(command) -> None:
    """페이지 크기·커서·대상 필터의 완전성을 검증한다."""
    if type(command.limit) is not int or not 1 <= command.limit <= 100:
        raise Types.ModerationError("invalid_input")
    if command.cursor is not None:
        validate_time(command.cursor.created_at, optional=False)
        if not isinstance(command.cursor.id, UUID):
            raise Types.ModerationError("invalid_input")
    if (command.target_type is None) != (command.target_id is None):
        raise Types.ModerationError("invalid_input")
    if command.target_type is not None:
        validate_target(command.target_type, command.target_id)


def _json_value(value):
    """UUID·시각·Decimal을 안정적인 멱등 비교 표현으로 변환한다."""
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, Decimal):
        return str(value.normalize())
    raise TypeError(f"Unsupported value: {type(value).__name__}")


def request_fingerprint(command, *, actor_id=None) -> str:
    """서버 시각·원본 변경과 무관한 정규화 요청의 SHA256을 계산한다."""
    payload = asdict(command)
    if actor_id is not None:
        payload["actor_id"] = str(actor_id)
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_value,
        allow_nan=False,
    )
    return hashlib.sha256(encoded.encode()).hexdigest()


def require_match(expected, actual) -> None:
    """멱등 키에 다른 입력이 재사용되면 충돌을 반환한다."""
    if expected != actual:
        raise Types.ModerationError("idempotency_conflict")


def require_info(info):
    """mapper가 변환한 미존재 결과를 업무 오류로 바꾼다."""
    if info is None:
        raise Types.ModerationError("not_found")
    return info


def legacy_review_status(info: Types.ReportInfo) -> str | None:
    """legacy provenance의 과거 검토 상태를 신규 intake와 구분한다."""
    return info.evidence_snapshot.get("legacy_moderation_flag", {}).get("status")


def action_request_info(info: Types.ActionInfo) -> Types.RequestActionCommand:
    """저장된 조치의 요청 필드만 복원해 변경 가능한 적용 상태를 비교에서 제외한다."""
    return Types.RequestActionCommand(
        assessment_id=info.assessment_id,
        target_type=info.target_type,
        target_id=info.target_id,
        action_type=info.action_type,
        scope=info.scope,
        starts_at=info.starts_at,
        ends_at=info.ends_at,
        idempotency_key=info.idempotency_key,
        reverses_action_id=info.reverses_action_id,
    )
