"""평가와 결과를 불변 이력으로 기록하며 자동 실행은 비활성화한다."""

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from app.db.idempotency import lock_key
from app.db.transaction import use_case_transaction
from app.modules.governance.moderation import types as Types
from app.modules.governance.moderation.mapper import persistence as PersistenceMapper
from app.modules.governance.moderation.repository import review as ReviewRepository
from app.modules.governance.moderation.service.util import (
    validation as ValidationServiceUtil,
)


def _normalize_assessment(
    command: Types.RecordAssessmentCommand,
) -> Types.RecordAssessmentCommand:
    """근거 신고 순서를 정규화하고 서로 충돌하는 중복 disposition을 거절한다."""
    ValidationServiceUtil.validate_target(command.target_type, command.target_id)
    for value in (command.evaluation_key, command.policy_version):
        ValidationServiceUtil.validate_text(value, maximum=200)
    ValidationServiceUtil.validate_text(command.rationale)
    if command.outcome not in {"violation", "no_violation", "insufficient_evidence"}:
        raise Types.ModerationError("invalid_input")
    if command.outcome == "violation":
        ValidationServiceUtil.validate_text(command.violation_code, maximum=100)
    elif command.violation_code is not None or command.severity is not None:
        raise Types.ModerationError("invalid_input")
    if command.severity is not None and (
        type(command.severity) is not int or not 0 <= command.severity <= 32767
    ):
        raise Types.ModerationError("invalid_input")
    if command.confidence_score is not None and (
        not isinstance(command.confidence_score, Decimal)
        or not command.confidence_score.is_finite()
        or not 0 <= command.confidence_score <= 1
    ):
        raise Types.ModerationError("invalid_input")
    ValidationServiceUtil.validate_time(command.window_start)
    ValidationServiceUtil.validate_time(command.window_end)
    if (command.window_start is None) != (command.window_end is None) or (
        command.window_start is not None and command.window_end <= command.window_start
    ):
        raise Types.ModerationError("invalid_input")
    if (
        not command.reports
        or len(command.reports) > 100
        or len(command.reviewer_notes) > 20
    ):
        raise Types.ModerationError("invalid_input")
    for note in command.reviewer_notes:
        ValidationServiceUtil.validate_text(note, maximum=1000)
    links = {}
    for link in command.reports:
        if not isinstance(link.report_id, UUID) or link.disposition not in {
            "supported",
            "not_supported",
            "insufficient_evidence",
            "unassessed",
        }:
            raise Types.ModerationError("invalid_input")
        if link.report_id in links and links[link.report_id] != link.disposition:
            raise Types.ModerationError("invalid_input")
        links[link.report_id] = link.disposition
    return replace(
        command,
        reports=tuple(
            Types.ReportDisposition(key, links[key]) for key in sorted(links, key=str)
        ),
    )


async def record_manual_assessment(
    session, command: Types.RecordAssessmentCommand, *, actor: Types.ActorCommand
) -> Types.AssessmentInfo:
    """활성 관리자의 판단과 근거를 원자 저장하고 재평가의 중복 분기를 거절한다."""
    actor_id = actor.user_id
    command = _normalize_assessment(command)
    fingerprint = ValidationServiceUtil.request_fingerprint(command, actor_id=actor_id)
    async with use_case_transaction(session):
        await ValidationServiceUtil._require_actor(session, actor_id, admin=True)
        await lock_key(session, "moderation.assessment", command.evaluation_key)
        row = await ReviewRepository.get_assessment_by_key(
            session, command.evaluation_key
        )
        existing = PersistenceMapper.assessment_row_to_info(row)
        if existing is not None:
            ValidationServiceUtil.require_match(
                existing.signals.get("request_fingerprint"), fingerprint
            )
            return existing
        # 접수 상태 편집과 평가를 같은 순서로 잠가 검토 중 거절·중복 전환을 막는다.
        await lock_key(session, "moderation.intake", "graph")
        await lock_key(
            session, "moderation.target", f"{command.target_type}:{command.target_id}"
        )
        previous_id = command.supersedes_assessment_id
        if previous_id is not None:
            row = await ReviewRepository.get_assessment(session, previous_id, lock=True)
            previous = ValidationServiceUtil.require_info(
                PersistenceMapper.assessment_row_to_info(row)
            )
            if (previous.target_type, previous.target_id) != (
                command.target_type,
                command.target_id,
            ):
                raise Types.ModerationError("invalid_link")
            row = await ReviewRepository.get_superseding_assessment(
                session, previous_id
            )
            if PersistenceMapper.scalar_row_to_value(row) is not None:
                raise Types.ModerationError("state_conflict")
            # 신규 ID만 생성하므로 정상 경로에서 순환은 없지만 기존 이력 훼손도 검사한다.
            visited = set()
            while previous is not None:
                if previous.id in visited:
                    raise Types.ModerationError("invalid_link")
                visited.add(previous.id)
                if previous.supersedes_assessment_id is None:
                    break
                row = await ReviewRepository.get_assessment(
                    session, previous.supersedes_assessment_id
                )
                previous = ValidationServiceUtil.require_info(
                    PersistenceMapper.assessment_row_to_info(row)
                )
                if (previous.target_type, previous.target_id) != (
                    command.target_type,
                    command.target_id,
                ):
                    raise Types.ModerationError("invalid_link")
        reporters = set()
        for link in command.reports:
            row = await ReviewRepository.get_report(session, link.report_id, lock=True)
            report = ValidationServiceUtil.require_info(
                PersistenceMapper.report_entity_to_info(row)
            )
            if (report.target_type, report.target_id) != (
                command.target_type,
                command.target_id,
            ) or report.intake_status != "received":
                raise Types.ModerationError("invalid_link")
            if (
                ValidationServiceUtil.legacy_review_status(report)
                in {"reviewed", "dismissed"}
                and not command.acknowledge_legacy_review
            ):
                raise Types.ModerationError("legacy_review_acknowledgement_required")
            if (
                command.window_start is not None
                and not command.window_start <= report.received_at < command.window_end
            ):
                raise Types.ModerationError("invalid_link")
            if report.reporter_user_id is not None:
                reporters.add(report.reporter_user_id)
        # 검증된 신호와 관리자 의견의 출처를 구분하며 전적·점수 공식은 만들지 않는다.
        values = {
            "target_type": command.target_type,
            "target_id": command.target_id,
            "assessment_type": "manual",
            "evaluator_user_id": actor_id,
            "policy_version": command.policy_version,
            "evaluated_at": datetime.now(UTC),
            "window_start": command.window_start,
            "window_end": command.window_end,
            "signals": {
                "request_fingerprint": fingerprint,
                "verified_report_count": len(command.reports),
                "verified_distinct_reporter_count": len(reporters),
                "reviewer_notes": list(command.reviewer_notes),
                "notes_source": "manual_unverified_observation",
            },
            "confidence_score": command.confidence_score,
            "outcome": command.outcome,
            "violation_code": command.violation_code,
            "severity": command.severity,
            "recommended_actions": [],
            "rationale": command.rationale,
            "supersedes_assessment_id": command.supersedes_assessment_id,
            "evaluation_key": command.evaluation_key,
        }
        row = await ReviewRepository.create_assessment(session, values, command.reports)
        result = PersistenceMapper.assessment_row_to_info(row)
        await ReviewRepository.create_admin_audit(
            session,
            actor_id,
            "moderation.assessment.record",
            result.id,
            {"outcome": result.outcome},
        )
        return result


async def record_automatic_assessment(
    session, command: Types.RecordAssessmentCommand
) -> Types.AssessmentInfo:
    """신뢰된 자동 실행 주체가 없어 쓰기 없이 명시적으로 거절한다."""
    raise Types.ModerationError("automatic_assessment_disabled")
