"""Trusted chat orchestration API: reserve once, then save messages and usage atomically."""

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import select

from app.db.idempotency import lock_key
from app.db.models.billing import UsageLog
from app.db.models.chat import Message
from app.db.models.product_usage import ProductGeneration
from app.db.models.snapshot.character import CharacterSnapshot
from app.db.models.snapshot.product import ProductSnapshotCharacter
from app.modules.chatting.conversation.service import owned_conversation
from app.modules.governance.admin.product_policy import ensure_available
from app.modules.llm.replacement import resolve_execution


@dataclass(frozen=True, slots=True)
class GeneratedMessage:
    product_character_id: UUID
    content: str


@dataclass(frozen=True, slots=True)
class GenerationResult:
    input_tokens: int
    output_tokens: int
    cost_credit: int
    messages: tuple[GeneratedMessage, ...] = ()
    outcome: Literal["succeeded", "failed", "cancelled"] = "succeeded"
    latency_ms: int | None = None


def result_digest(value):
    if value.outcome not in ("succeeded", "failed", "cancelled"):
        raise ValueError("Invalid outcome.")
    for n, maximum in (
        (value.input_tokens, 2**31 - 1),
        (value.output_tokens, 2**31 - 1),
        (value.cost_credit, 2**63 - 1),
    ):
        if type(n) is not int or not 0 <= n <= maximum:
            raise ValueError(
                "Usage must be nonnegative integers within storage limits."
            )
    if value.latency_ms is not None and (
        type(value.latency_ms) is not int or not 0 <= value.latency_ms < 2**31
    ):
        raise ValueError("Invalid latency.")
    if (value.outcome == "succeeded") != bool(value.messages) or len(
        value.messages
    ) > 100:
        raise ValueError("Successful output needs 1–100 messages; failures have none.")
    if any(not m.content.strip() or len(m.content) > 200000 for m in value.messages):
        raise ValueError("Invalid generated message.")
    return hashlib.sha256(
        json.dumps(asdict(value), sort_keys=True, default=str).encode()
    ).hexdigest()


def info(run, *, created=False):
    return {
        "id": run.id,
        "created": created,
        "status": run.status,
        "product_snapshot_id": run.product_snapshot_id,
        "model_id": run.model_id,
        "model_name": run.model_name,
        "reasoning_effort": run.reasoning_effort,
        "message_count": run.message_count,
    }


async def begin_generation(
    session, *, conversation_id, user_id, request_key, input_text
):
    if (
        not request_key.strip()
        or len(request_key) > 128
        or not input_text.strip()
        or len(input_text) > 200000
    ):
        raise ValueError("Invalid generation request.")
    digest = hashlib.sha256(input_text.encode()).hexdigest()
    async with session.begin():
        await lock_key(session, "generation", f"{user_id}:{request_key}")
        existing = await session.scalar(
            select(ProductGeneration).where(
                ProductGeneration.user_id == user_id,
                ProductGeneration.request_key == request_key,
            )
        )
        if existing:
            if (
                existing.conversation_id != conversation_id
                or existing.input_digest != digest
            ):
                raise ValueError("Request key was already used with different input.")
            return info(existing)
        conversation = await owned_conversation(
            session, conversation_id, user_id, lock=True
        )
        if not conversation.product_snapshot_id:
            raise ValueError("Legacy version must be verified before generation.")
        await ensure_available(session, conversation.product_snapshot_id)
        execution = await resolve_execution(
            session, snapshot_id=conversation.product_snapshot_id
        )
        run = ProductGeneration(
            id=uuid4(),
            user_id=user_id,
            conversation_id=conversation.id,
            product_id=conversation.product_id,
            product_snapshot_id=conversation.product_snapshot_id,
            model_id=execution["model_id"],
            model_name=execution["model"],
            reasoning_effort=execution["reasoning_effort"],
            request_key=request_key,
            input_digest=digest,
            status="pending",
            message_count=0,
        )
        session.add(run)
        await session.flush()
        session.add(
            Message(
                conversation_id=conversation.id,
                product_snapshot_id=run.product_snapshot_id,
                generation_id=run.id,
                sender_type="user",
                content=input_text,
                generated_by_ai=False,
            )
        )
        await session.flush()
        return info(run, created=True)


async def finish_generation(
    session, *, generation_id, user_id, value: GenerationResult
):
    fingerprint = result_digest(value)
    async with session.begin():
        run = await session.scalar(
            select(ProductGeneration)
            .where(
                ProductGeneration.id == generation_id,
                ProductGeneration.user_id == user_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if run is None:
            raise LookupError("Generation not found.")
        if run.status != "pending":
            if run.result_digest != fingerprint:
                raise ValueError("Generation already finished with different output.")
            return info(run)
        conversation = await owned_conversation(
            session, run.conversation_id, user_id, lock=True
        )
        status = value.outcome
        if status == "succeeded":
            if conversation.product_snapshot_id != run.product_snapshot_id:
                status = "stale"
            else:
                try:
                    await ensure_available(session, run.product_snapshot_id)
                except ValueError:
                    status = "stale"
        if status == "succeeded":
            for output in value.messages:
                character = await session.scalar(
                    select(ProductSnapshotCharacter).where(
                        ProductSnapshotCharacter.id == output.product_character_id,
                        ProductSnapshotCharacter.product_snapshot_id
                        == run.product_snapshot_id,
                    )
                )
                if character is None:
                    raise ValueError(
                        "Output character is not in the generation version."
                    )
                source = await session.get(
                    CharacterSnapshot, character.character_snapshot_id
                )
                session.add(
                    Message(
                        conversation_id=run.conversation_id,
                        product_snapshot_id=run.product_snapshot_id,
                        generation_id=run.id,
                        product_character_id=character.id,
                        character_id=source.character_id,
                        sender_type="character",
                        content=output.content,
                        model_id=run.model_id,
                        generated_by_ai=True,
                    )
                )
        now = datetime.now(UTC)
        # Actual provider cost is retained even for stale/failed/cancelled output.
        session.add(
            UsageLog(
                user_id=user_id,
                conversation_id=run.conversation_id,
                generation_id=run.id,
                product_id=run.product_id,
                product_snapshot_id=run.product_snapshot_id,
                model_id=run.model_id,
                reasoning_effort=run.reasoning_effort,
                input_tokens=value.input_tokens,
                output_tokens=value.output_tokens,
                cost_credit=value.cost_credit,
                latency_ms=value.latency_ms,
                created_at=now,
            )
        )
        run.status, run.result_digest, run.finished_at = status, fingerprint, now
        run.message_count = len(value.messages) if status == "succeeded" else 0
        await session.flush()
        return info(run)
