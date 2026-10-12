"""신고 접수와 관리자 접수 상태 변경."""

from datetime import UTC, datetime
from uuid import UUID

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
from app.modules.identity import types as IdentityTypes
from app.modules.identity.service import query as IdentityQueryService


async def _capture_report_target(session, command, actor_id):
    """공개 도메인 서비스로 신고 접근 권한과 버전을 검증하고 최소 증거를 확보한다."""
    try:
        if command.target_type == "user":
            target_id = await IdentityQueryService.get_reportable_user(
                session, IdentityTypes.GetUserCommand(command.target_id)
            )
            if command.target_snapshot_id is not None:
                raise Types.ModerationError("invalid_input")
            return None, None, {"target_user_id": str(target_id)}
        product = await ProductQueryService.get_accessible_product(
            session,
            ProductTypes.GetAccessibleProductCommand(
                product_id=command.target_id, user_id=actor_id, lock=True
            ),
        )
        snapshot_id = command.target_snapshot_id or product.latest_snapshot_id
        if snapshot_id is None:
            raise Types.ModerationError("target_unavailable")
        snapshot = await ProductQueryService.ensure_snapshot_available(
            session, ProductTypes.ProductSnapshotCommand(snapshot_id)
        )
        if snapshot.product_id != product.id:
            raise Types.ModerationError("target_unavailable")
        # 전체 캐릭터 설정이나 비공개 내부 문맥은 복제하지 않는다.
        data = snapshot.snapshot_data.get("product", snapshot.snapshot_data)
        return (
            product.owner_id,
            snapshot.id,
            {
                "snapshot_id": str(snapshot.id),
                "version": snapshot.version,
                "title": data.get("title"),
                "description": data.get("description"),
                "opening_message": data.get("opening_message"),
            },
        )
    except LookupError as exc:
        raise Types.ModerationError("target_unavailable") from exc
    except ValueError as exc:
        raise Types.ModerationError("target_unavailable") from exc


async def submit_report(
    session, command: Types.SubmitReportCommand, *, actor: Types.ActorCommand
) -> Types.ReportSummaryInfo:
    """활성 신고자의 접수를 멱등 저장하고 신고자에게 허용된 요약만 반환한다."""
    actor_id = actor.user_id
    ValidationServiceUtil.validate_target(command.target_type, command.target_id)
    if command.target_type not in {"user", "product"}:
        raise Types.ModerationError("target_unsupported")
    if not isinstance(command.request_key, UUID):
        raise Types.ModerationError("invalid_input")
    ValidationServiceUtil.validate_text(command.reason_code, maximum=100)
    if command.reason_code == "legacy_unclassified":
        raise Types.ModerationError("invalid_input")
    if command.reason_detail is not None:
        ValidationServiceUtil.validate_text(command.reason_detail)
    ValidationServiceUtil.validate_time(command.occurred_at)
    if command.form_elapsed_ms is not None and (
        type(command.form_elapsed_ms) is not int
        or not 0 <= command.form_elapsed_ms <= 2**63 - 1
    ):
        raise Types.ModerationError("invalid_input")
    if len(command.attachment_claims) > 10:
        raise Types.ModerationError("invalid_input")
    for claim in command.attachment_claims:
        ValidationServiceUtil.validate_text(claim, maximum=1000)
    fingerprint = ValidationServiceUtil.request_fingerprint(command, actor_id=actor_id)
    async with use_case_transaction(session):
        # 인증 상태를 먼저 확인하고, 기존 요청이 있으면 변한 원본을 재확보하지 않는다.
        await ValidationServiceUtil._require_actor(session, actor_id)
        await lock_key(session, "moderation.report", str(command.request_key))
        row = await ReviewRepository.get_report_by_key(session, command.request_key)
        existing = PersistenceMapper.report_entity_to_info(row)
        if existing is not None:
            ValidationServiceUtil.require_match(
                existing.evidence_snapshot.get("request_fingerprint"), fingerprint
            )
            return PersistenceMapper.report_info_to_summary(existing)
        owner_id, snapshot_id, evidence = await _capture_report_target(
            session, command, actor_id
        )
        now = datetime.now(UTC)
        row = await ReviewRepository.create_report(
            session,
            {
                "request_key": command.request_key,
                "reporter_user_id": actor_id,
                "target_type": command.target_type,
                "target_id": command.target_id,
                "target_owner_user_id": owner_id,
                "target_snapshot_id": snapshot_id,
                "reason_code": command.reason_code,
                "reason_detail": command.reason_detail,
                "occurred_at": command.occurred_at,
                "received_at": now,
                "form_elapsed_ms": command.form_elapsed_ms,
                "evidence_snapshot": {
                    "server": evidence,
                    "request_fingerprint": fingerprint,
                },
                "attachment_refs": [
                    {"source": "reporter_claim", "reference": item}
                    for item in command.attachment_claims
                ],
                "evidence_captured_at": now,
                "intake_status": "received",
            },
        )
        return PersistenceMapper.report_info_to_summary(
            PersistenceMapper.report_entity_to_info(row)
        )


async def change_report_intake(
    session, command: Types.ChangeReportIntakeCommand, *, actor: Types.ActorCommand
) -> Types.ReportInfo:
    """관리자가 미처리 신고를 중복·거절로 확정하며 연결 순환을 차단한다."""
    actor_id = actor.user_id
    ValidationServiceUtil.validate_text(command.reason)
    if command.intake_status not in {"duplicate", "rejected"} or (
        (command.intake_status == "duplicate")
        != (command.duplicate_of_report_id is not None)
    ):
        raise Types.ModerationError("invalid_input")
    async with use_case_transaction(session):
        await ValidationServiceUtil._require_actor(session, actor_id, admin=True)
        # 모든 중복 그래프 편집을 직렬화해 서로를 동시에 연결하는 경쟁을 막는다.
        await lock_key(session, "moderation.intake", "graph")
        row = await ReviewRepository.get_report(session, command.report_id, lock=True)
        info = ValidationServiceUtil.require_info(
            PersistenceMapper.report_entity_to_info(row)
        )
        if (info.intake_status, info.duplicate_of_report_id, info.intake_reason) == (
            command.intake_status,
            command.duplicate_of_report_id,
            command.reason,
        ):
            return info
        if (
            info.intake_status != "received"
            or ValidationServiceUtil.legacy_review_status(info)
            in {"reviewed", "dismissed"}
        ):
            raise Types.ModerationError("state_conflict")
        row = await ReviewRepository.get_report_assessment_id(session, info.id)
        if PersistenceMapper.scalar_row_to_value(row) is not None:
            raise Types.ModerationError("state_conflict")
        visited = {info.id}
        next_id = command.duplicate_of_report_id
        while next_id is not None:
            if next_id in visited:
                raise Types.ModerationError("invalid_link")
            visited.add(next_id)
            row = await ReviewRepository.get_report(session, next_id)
            parent = ValidationServiceUtil.require_info(
                PersistenceMapper.report_entity_to_info(row)
            )
            if (parent.target_type, parent.target_id) != (
                info.target_type,
                info.target_id,
            ) or parent.intake_status == "rejected":
                raise Types.ModerationError("invalid_link")
            next_id = parent.duplicate_of_report_id
        row = await ReviewRepository.update_report_intake(
            session,
            info.id,
            status=command.intake_status,
            duplicate_id=command.duplicate_of_report_id,
            reason=command.reason,
        )
        result = PersistenceMapper.report_entity_to_info(row)
        await ReviewRepository.create_admin_audit(
            session,
            actor_id,
            "moderation.report.intake",
            result.id,
            {"status": result.intake_status},
        )
        return result
