"""Inspect one answer, or explicitly retry its stored finalization after investigation."""

import argparse
import asyncio
import json
import os
from datetime import UTC, datetime
from typing import NoReturn
from uuid import UUID

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.modules.chatting.chat import types as ChatTypes
from app.modules.chatting.chat.service.query import (
    answer_recovery as ChatAnswerRecoveryQueryService,
)
from app.modules.chatting.chat.service.query import (
    generation as ChatGenerationQueryService,
)
from app.modules.chatting.chat.service.workflow.answers import AnswerOrchestrator
from app.modules.chatting.memory import service as MemoryService
from app.modules.llm.service import EmbeddingService, TextGenerationService


async def run_recovery(
    generation_id: UUID,
    user_id: UUID,
    *,
    retry: bool = False,
    operator: str | None = None,
    reason: str | None = None,
) -> int:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as session:
            run = await ChatGenerationQueryService.get_generation_state(
                session,
                ChatTypes.GetGenerationStateCommand(
                    generation_id=generation_id, user_id=user_id
                ),
            )
            attempts = (
                await ChatAnswerRecoveryQueryService.list_answer_recovery_attempts(
                    session,
                    ChatTypes.GetGenerationStateCommand(
                        generation_id=generation_id, user_id=user_id
                    ),
                )
            )
        print(
            json.dumps(
                {
                    "generation_id": str(run.id),
                    "status": run.status,
                    "phase": (run.answer_metadata or {}).get("phase"),
                    "attempt_count": run.answer_recovery_attempts,
                    "next_attempt_at": run.answer_recovery_next_at.isoformat()
                    if run.answer_recovery_next_at
                    else None,
                    "quarantined_at": run.answer_recovery_quarantined_at.isoformat()
                    if run.answer_recovery_quarantined_at
                    else None,
                    "attempts": [
                        {
                            "attempt_count": item.attempt_count,
                            "started_at": item.started_at.isoformat(),
                            "failure_class": item.failure_class,
                            "manual": item.manual,
                        }
                        for item in attempts
                    ],
                }
            )
        )
        if retry:
            orchestrator = AnswerOrchestrator(
                sessions,
                TextGenerationService(()),
                MemoryService.MemoryRetriever(sessions, EmbeddingService(())),
            )
            result = await orchestrator.recover_answer(
                ChatTypes.ClaimAnswerRecoveryCommand(
                    generation_id=generation_id,
                    user_id=user_id,
                    now=datetime.now(UTC),
                    operator=operator,
                    reason=reason,
                )
            )
            print(
                json.dumps(
                    {
                        "generation_id": str(result.generation_id),
                        "status": result.status,
                    }
                )
            )
            return int(result.status == "pending")
        return 0
    except Exception as exc:  # noqa: BLE001 - CLI prints safe types, never SQL or provider details
        print(json.dumps({"error_kind": type(exc).__name__}))
        return 1
    finally:
        await engine.dispose()


def main() -> NoReturn:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generation-id", type=UUID, required=True)
    parser.add_argument("--user-id", type=UUID, required=True)
    parser.add_argument("--retry", action="store_true")
    parser.add_argument("--operator")
    parser.add_argument("--reason")
    args = parser.parse_args()
    if args.retry and (not args.operator or not args.reason):
        parser.error("--retry requires --operator and --reason")
    if not args.retry and (args.operator is not None or args.reason is not None):
        parser.error("--operator and --reason require --retry")
    raise SystemExit(
        asyncio.run(
            run_recovery(
                args.generation_id,
                args.user_id,
                retry=args.retry,
                operator=args.operator,
                reason=args.reason,
            )
        )
    )


if __name__ == "__main__":
    main()
