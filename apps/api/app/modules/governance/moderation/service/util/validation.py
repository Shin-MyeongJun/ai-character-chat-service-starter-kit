"""업무 입력 검증·인가·멱등 비교의 내부 보조 함수."""

import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from typing import TypeVar, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.governance.moderation import types as Types
from app.modules.identity import types as IdentityTypes
from app.modules.identity.service import query as IdentityQueryService

TARGETS = {"user", "product", "character", "message"}
InfoT = TypeVar(
    "InfoT", bound=Types.ReportInfo | Types.AssessmentInfo | Types.ActionInfo
)


async def _require_actor(
    session: AsyncSession, actor_id: object, *, admin: bool = False
) -> None:
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


def validate_text(value: object, *, maximum: int = 4000) -> None:
    """미검증 값을 받아 비어 있지 않은 제한 길이의 str만 허용한다. 원문은 유지한다."""
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise Types.ModerationError("invalid_input")


def validate_time(value: object, *, optional: bool = True) -> None:
    """aware datetime을 허용하고 optional일 때만 None을 허용한다. 변환은 없다."""
    if value is None and optional:
        return
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise Types.ModerationError("invalid_input")


def validate_target(target_type: object, target_id: object) -> None:
    """지원 대상 종류와 UUID 식별자를 검증한다."""
    if target_type not in TARGETS or not isinstance(target_id, UUID):
        raise Types.ModerationError("invalid_input")


def validate_page(
    command: Types.ListReportsCommand
    | Types.ListAssessmentsCommand
    | Types.ListActionsCommand,
) -> None:
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


def _json_value(value: object) -> str:
    """UUID·시각·Decimal을 안정적인 멱등 비교 표현으로 변환한다."""
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, Decimal):
        return str(value.normalize())
    raise TypeError(f"Unsupported value: {type(value).__name__}")


def request_fingerprint(
    command: Types.SubmitReportCommand
    | Types.RecordAssessmentCommand
    | Types.RequestActionCommand,
    *,
    actor_id: UUID | None = None,
) -> str:
    """서버 시각·원본 변경과 무관한 정규화 요청의 SHA256을 계산한다."""
    # asdict는 dataclass의 재귀 값(Decimal/UUID/tuple 포함)을 반환한다.
    # JSON 변환·거절은 아래 dumps/default에 그대로 맡긴다.
    payload: dict[str, object] = asdict(command)
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


def require_match(expected: object, actual: object) -> None:
    """멱등 키에 다른 입력이 재사용되면 충돌을 반환한다."""
    if expected != actual:
        raise Types.ModerationError("idempotency_conflict")


def require_info(info: InfoT | None) -> InfoT:
    """mapper가 변환한 미존재 결과를 업무 오류로 바꾼다."""
    if info is None:
        raise Types.ModerationError("not_found")
    return info


def legacy_review_status(info: Types.ReportInfo) -> str | None:
    """legacy provenance의 과거 검토 상태를 신규 intake와 구분한다."""
    # 0027 이관이 만드는 legacy object의 status는 원래 문자열이다.
    # 누락 기본값과 명시적 null/손상 데이터의 기존 동작을 그대로 유지한다.
    legacy = cast(
        Types.LegacyModerationFlag,
        info.evidence_snapshot.get("legacy_moderation_flag", {}),
    )
    return legacy.get("status")


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
