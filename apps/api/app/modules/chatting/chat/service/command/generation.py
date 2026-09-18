# 사용자 범위 request_key로 생성 사실을 예약하고 완료 결과 digest로 중복 완료를 비교한다.
# LLM 호출은 하지 않는다. 완료 시 메시지·usage·통계 예약을 같은 DB 트랜잭션에 반영한다.
"Trusted chat orchestration API: reserve once, then save messages and usage atomically."

import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime

from app.db.idempotency import lock_key
from app.db.transaction import use_case_transaction
from app.modules.chatting.chat import repository as Repository
from app.modules.chatting.chat import types as Types
from app.modules.chatting.chat.mapper import persistence as PersistenceMapper
from app.modules.chatting.chat.mapper.persistence import (
    generation_record_to_info,
)
from app.modules.chatting.chat.service.command.messages import _ensure_idle
from app.modules.chatting.chat.types import GenerationInfo
from app.modules.chatting.conversation import types as ConversationTypes
from app.modules.chatting.conversation.service import (
    get_owned_conversation,
    list_conversation_characters,
)
from app.modules.commerce.billing import service as BillingService
from app.modules.commerce.billing import types as BillingTypes
from app.modules.content.product import types as ProductTypes
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


# 소유 대화와 사용자 범위 요청 키를 확인해 pending 생성을 예약한다.
# input_message_id가 있으면 기존 마지막 사용자 입력을 재사용하고, 없으면 입력 메시지를 저장한다.
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
    digest_input = (
        input_text
        if command.input_message_id is None
        else json.dumps(
            [str(command.input_message_id), command.expected_revision, input_text]
        )
    )
    digest = hashlib.sha256(digest_input.encode()).hexdigest()
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
            ConversationTypes.OwnedConversationCommand(
                conversation_id=conversation_id, user_id=user_id, lock=True
            ),
        )
        await _ensure_idle(session, conversation_id)
        if command.input_message_id is not None:
            message = PersistenceMapper.message_entity_to_info(
                await Repository.get_last_message(session, conversation_id)
            )
            if (
                message is None
                or message.id != command.input_message_id
                or message.sender_type != "user"
                or message.revision != command.expected_revision
                or message.content != input_text
            ):
                raise Types.MessageConflictError(
                    "Input must reference the current last user message and revision."
                )
        if not conversation.product_snapshot_id:
            raise ValueError("Legacy version must be verified before generation.")
        await ensure_available(
            session,
            ProductTypes.EnsureAvailableCommand(
                snapshot_id=conversation.product_snapshot_id
            ),
        )
        execution = command.execution or await resolve_execution(
            session,
            LlmTypes.ResolveExecutionCommand(
                snapshot_id=conversation.product_snapshot_id
            ),
        )
        row = await Repository.create_generation(
            session,
            conversation,
            execution,
            user_id,
            request_key,
            digest,
            input_text,
            command.input_message_id,
        )
        return generation_record_to_info(row, created=True)


# 생성 결과·사용량을 확정한다. 버전이 바뀐 결과는 stale로 남겨 출력 메시지를 추가하지 않는다.
# 이미 확정된 생성의 재전송은 결과 digest가 같아야 하며 사용량을 다시 쓰지 않는다.
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
        conversation = await get_owned_conversation(
            session,
            ConversationTypes.OwnedConversationCommand(
                conversation_id=run.conversation_id, user_id=user_id, lock=True
            ),
        )
        # All history writers lock conversation first, then generation records.
        row = await Repository.get_owned_generation(
            session, generation_id, user_id, lock=True
        )
        run = PersistenceMapper.generation_entity_to_state_info(row)
        assert run is not None
        if run.status != "pending":
            if run.result_digest != fingerprint:
                raise ValueError("Generation already finished with different output.")
            return generation_record_to_info(run)
        # 성공 결과라도 사용 버전이 바뀌거나 만료되면 stale로 저장하고 출력 메시지는 추가하지 않는다.
        # 아래 usage 기록은 stale·실패·취소에도 실행된다.
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
            participants = await list_conversation_characters(
                session,
                ConversationTypes.OwnedConversationCommand(
                    conversation_id=run.conversation_id, user_id=user_id
                ),
            )
            characters = {c.product_character_id: c.character_id for c in participants}
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
