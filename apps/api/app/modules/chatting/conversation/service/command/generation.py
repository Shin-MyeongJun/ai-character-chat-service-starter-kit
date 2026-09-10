"Trusted chat orchestration API: reserve once, then save messages and usage atomically."

import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime

from app.db.idempotency import lock_key
from app.db.transaction import use_case_transaction
from app.modules.chatting.conversation import repository as Repository
from app.modules.chatting.conversation import types as Types
from app.modules.chatting.conversation.mapper import persistence as PersistenceMapper
from app.modules.chatting.conversation.mapper.persistence import (
    generation_record_to_info,
)
from app.modules.chatting.conversation.service import get_owned_conversation
from app.modules.chatting.conversation.types import GenerationInfo
from app.modules.commerce.billing import service as BillingService
from app.modules.commerce.billing import types as BillingTypes
from app.modules.content.product import types as ProductTypes
from app.modules.content.product.service import views as ProductViewsService
from app.modules.content.product.service.command.statistics_queue import (
    mark_statistics_dirty,
)
from app.modules.content.product.service.query import ensure_available
from app.modules.llm import types as LlmTypes
from app.modules.llm.service.replacement import resolve_execution


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


async def begin_generation(
    session, command: Types.BeginGenerationCommand
) -> GenerationInfo:
    conversation_id = command.conversation_id
    user_id = command.user_id
    request_key = command.request_key
    input_text = command.input_text
    if (
        not request_key.strip()
        or len(request_key) > 128
        or (not input_text.strip())
        or (len(input_text) > 200000)
    ):
        raise ValueError("Invalid generation request.")
    digest = hashlib.sha256(input_text.encode()).hexdigest()
    async with use_case_transaction(session):
        await lock_key(session, "generation", f"{user_id}:{request_key}")
        row = await Repository.get_generation_by_request(session, user_id, request_key)
        existing = PersistenceMapper.generation_entity_to_state_info(row)
        if existing:
            if (
                existing.conversation_id != conversation_id
                or existing.input_digest != digest
            ):
                raise ValueError("Request key was already used with different input.")
            return generation_record_to_info(existing)
        conversation = await get_owned_conversation(
            session,
            Types.OwnedConversationCommand(
                conversation_id=conversation_id, user_id=user_id, lock=True
            ),
        )
        if not conversation.product_snapshot_id:
            raise ValueError("Legacy version must be verified before generation.")
        await ensure_available(
            session,
            ProductTypes.EnsureAvailableCommand(
                snapshot_id=conversation.product_snapshot_id
            ),
        )
        execution = await resolve_execution(
            session,
            LlmTypes.ResolveExecutionCommand(
                snapshot_id=conversation.product_snapshot_id
            ),
        )
        row = await Repository.create_generation(
            session, conversation, execution, user_id, request_key, digest, input_text
        )
        return generation_record_to_info(row, created=True)


async def finish_generation(
    session, command: Types.FinishGenerationCommand
) -> GenerationInfo:
    generation_id = command.generation_id
    user_id = command.user_id
    value = command.value
    fingerprint = result_digest(value)
    async with use_case_transaction(session):
        row = await Repository.get_owned_generation(session, generation_id, user_id)
        run = PersistenceMapper.generation_entity_to_state_info(row)
        if run is None:
            raise LookupError("Generation not found.")
        if run.status != "pending":
            if run.result_digest != fingerprint:
                raise ValueError("Generation already finished with different output.")
            return generation_record_to_info(run)
        conversation = await get_owned_conversation(
            session,
            Types.OwnedConversationCommand(
                conversation_id=run.conversation_id, user_id=user_id, lock=True
            ),
        )
        status: str = value.outcome
        if status == "succeeded":
            if conversation.product_snapshot_id != run.product_snapshot_id:
                status = "stale"
            else:
                try:
                    await ensure_available(
                        session,
                        ProductTypes.EnsureAvailableCommand(
                            snapshot_id=run.product_snapshot_id
                        ),
                    )
                except ValueError:
                    status = "stale"
        if status == "succeeded":
            runtime = await ProductViewsService.get_snapshot_runtime(
                session, ProductTypes.ProductSnapshotCommand(run.product_snapshot_id)
            )
            characters = {
                c.id: runtime.characters[c.character_snapshot_id].character_id
                for c in runtime.composition.characters
            }
            for output in value.messages:
                if output.product_character_id not in characters:
                    raise ValueError(
                        "Output character is not in the generation version."
                    )
                await Repository.add_generation_message(
                    session, run, output, characters[output.product_character_id]
                )
        now = datetime.now(UTC)
        await BillingService.record_usage(
            session,
            BillingTypes.RecordUsageCommand(
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
            ),
        )
        row = await Repository.finish_generation(
            session,
            run.id,
            status,
            fingerprint,
            now,
            len(value.messages) if status == "succeeded" else 0,
        )
        result = generation_record_to_info(row)
        await mark_statistics_dirty(
            session, ProductTypes.MarkStatisticsDirtyCommand(run.product_id, now)
        )
        return result
