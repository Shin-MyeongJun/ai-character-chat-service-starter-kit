"""Durable recovery admission. All writers lock conversation then generation."""

from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.chatting.chat import repository as Repository
from app.modules.chatting.chat import types as Types
from app.modules.chatting.chat.service.command import (
    generation as GenerationCommandService,
)


def validate_recovery_command(command: Types.ClaimAnswerRecoveryCommand) -> None:
    manual = command.operator is not None or command.reason is not None
    if command.now.tzinfo is None:
        raise ValueError("Recovery time must include a timezone.")
    if manual and (
        command.operator is None
        or not 1 <= len(command.operator.strip()) <= 120
        or command.reason is None
        or not 1 <= len(command.reason.strip()) <= 1000
    ):
        raise ValueError(
            "Manual recovery requires an operator and investigation reason."
        )


async def claim_answer_recovery(
    session: AsyncSession, command: Types.ClaimAnswerRecoveryCommand
) -> Types.AnswerRecoveryClaimInfo:
    validate_recovery_command(command)
    manual = command.operator is not None
    async with GenerationCommandService._locked_generation(
        session,
        Types.GetGenerationStateCommand(
            generation_id=command.generation_id, user_id=command.user_id
        ),
    ) as locked:
        run = locked.run
        if run.status != "pending":
            return Types.AnswerRecoveryClaimInfo(run, None)
        staged = (run.answer_metadata or {}).get("phase") == "result_ready"
        if not staged and (
            run.answer_lease_until is None or run.answer_lease_until > command.now
        ):
            return Types.AnswerRecoveryClaimInfo(run, None)
        if (
            run.answer_recovery_next_at is not None
            and run.answer_recovery_next_at > command.now
        ):
            return Types.AnswerRecoveryClaimInfo(run, None)
        if not manual and (
            run.answer_recovery_quarantined_at is not None
            or run.answer_recovery_attempts >= Types.ANSWER_RECOVERY_MAX_ATTEMPTS
        ):
            return Types.AnswerRecoveryClaimInfo(run, None)
        attempt_count = run.answer_recovery_attempts + 1
        next_at = command.now + timedelta(
            seconds=min(900, 30 * 2 ** min(attempt_count - 1, 5))
        )
        quarantined_at = run.answer_recovery_quarantined_at
        if manual or attempt_count >= Types.ANSWER_RECOVERY_MAX_ATTEMPTS:
            quarantined_at = quarantined_at or command.now
        await Repository.claim_answer_recovery(
            session, command, attempt_count, next_at, quarantined_at
        )
        return Types.AnswerRecoveryClaimInfo(run, attempt_count)


async def record_answer_recovery_failure(
    session: AsyncSession, command: Types.RecordAnswerRecoveryFailureCommand
) -> None:
    async with GenerationCommandService._locked_generation(
        session,
        Types.GetGenerationStateCommand(
            generation_id=command.generation_id, user_id=command.user_id
        ),
    ) as locked:
        run = locked.run
        # A late failure must not overwrite a newer attempt or a terminal fact.
        if (
            run.status != "pending"
            or run.answer_recovery_attempts != command.attempt_count
        ):
            return
        quarantined_at = run.answer_recovery_quarantined_at
        if command.failure_class in {"invariant", "internal", "storage_constraint"}:
            quarantined_at = quarantined_at or command.now
        await Repository.record_answer_recovery_failure(
            session, command, quarantined_at
        )
