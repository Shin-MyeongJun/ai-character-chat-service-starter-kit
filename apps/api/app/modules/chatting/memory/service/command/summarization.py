# 미요약 메시지의 추정 크기로 오래된 배치를 선택한다. 최근 원문은 남기며 요약해도 원문을 삭제하지 않는다.
# save_summary는 호출자가 잠금·원문 재검증·트랜잭션을 확보한 뒤 사용하는 저장 단계다.
from __future__ import annotations

import hashlib
import json
from math import ceil

from app.modules.chatting.memory import repository as Repository
from app.modules.chatting.memory import types as Types
from app.modules.chatting.memory.mapper import persistence as PersistenceMapper
from app.modules.llm import service as LLMService
from app.modules.llm import types as LLMTypes


def estimate_tokens(text: str) -> int:
    """Cheap conservative-ish estimate; provider tokenizers remain authoritative."""
    return max(1, ceil(len(text.encode("utf-8")) / 4))


def _message_tokens(message: Types.SourceMessageInfo) -> int:
    return estimate_tokens(f"{message.sender_type}: {message.content}\n")


def _validate_policy(policy: Types.MemoryPolicy) -> None:
    integer_values = (
        policy.summarization_threshold_tokens,
        policy.summary_batch_tokens,
        policy.recent_raw_tokens,
        policy.summary_output_tokens,
        policy.memory_token_budget,
        policy.retrieval_candidates,
        policy.retrieval_limit,
    )
    if any(type(value) is not int or value < 1 for value in integer_values):
        raise ValueError(
            "Memory policy token and count values must be positive integers."
        )
    if policy.summary_batch_tokens > policy.summarization_threshold_tokens:
        raise ValueError("Summary batch tokens must not exceed the trigger threshold.")
    if not policy.prompt_version.strip() or len(policy.prompt_version) > 100:
        raise ValueError(
            "Prompt version must be a non-blank value up to 100 characters."
        )


def _source_digest(messages: tuple[Types.SourceMessageInfo, ...]) -> str:
    payload = [
        [str(item.id), item.sender_type, item.content, item.position, item.revision]
        for item in messages
    ]
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


# 미요약 메시지에서 최근 원문을 남기고 오래된 배치를 선택한다. 임계치 미달이면 None이다.
def plan_summarization(
    command: Types.PlanSummarizationCommand,
) -> Types.SummaryPlanInfo | None:
    _validate_policy(command.policy)
    messages = tuple(sorted(command.messages, key=lambda item: item.position))
    if any(
        item.position < 1
        or item.revision < 1
        or not item.content.strip()
        or item.sender_type not in {"user", "character", "system"}
        for item in messages
    ):
        raise ValueError("Summary sources contain an invalid saved message.")
    if len({item.position for item in messages}) != len(messages):
        raise ValueError("Summary source positions must be unique.")
    token_counts = [_message_tokens(item) for item in messages]
    if sum(token_counts) < command.policy.summarization_threshold_tokens:
        return None

    protected_start = len(messages)
    protected_tokens = 0
    while protected_start > 0 and protected_tokens < command.policy.recent_raw_tokens:
        protected_start -= 1
        protected_tokens += token_counts[protected_start]
    eligible = messages[:protected_start]
    eligible_tokens = token_counts[:protected_start]
    if not eligible:
        return None

    end = 0
    selected_tokens = 0
    while end < len(eligible):
        next_tokens = eligible_tokens[end]
        # 첫 메시지 하나는 배치 예산보다 길어도 통째로 선택한다. 메시지 내부를 자르지 않는 현재 경계다.
        if end and selected_tokens + next_tokens > command.policy.summary_batch_tokens:
            break
        selected_tokens += next_tokens
        end += 1
    selected = eligible[:end]
    return Types.SummaryPlanInfo(
        conversation_id=command.conversation_id,
        owner_id=command.owner_id,
        conversation_revision=command.conversation_revision,
        source_messages=selected,
        source_digest=_source_digest(selected),
        estimated_input_tokens=selected_tokens,
        prompt_version=command.policy.prompt_version,
    )


# 요약 생성 중 원문이 수정·삭제되었는지 revision과 범위 digest로 검사한다. 단순 뒤쪽 append와 구분한다.
def validate_summary_source(command: Types.ValidateSummarySourceCommand) -> None:
    if command.current_conversation_revision != command.plan.conversation_revision:
        raise Types.StaleMemoryWorkError("Conversation history revision changed.")
    current = tuple(sorted(command.current_messages, key=lambda item: item.position))
    if (
        current != command.plan.source_messages
        or _source_digest(current) != command.plan.source_digest
    ):
        raise Types.StaleMemoryWorkError("Summary source messages changed.")


class SummaryGenerator:
    def __init__(
        self, text_generation_service: LLMService.TextGenerationService
    ) -> None:
        self._text_generation_service = text_generation_service

    async def generate_summary(
        self, command: Types.GenerateSummaryCommand
    ) -> Types.GeneratedSummaryInfo:
        if not command.model.strip() or command.max_output_tokens < 1:
            raise ValueError("Summary model and output budget are required.")
        transcript = "\n".join(
            f"[{item.position}] {item.sender_type}: {item.content}"
            for item in command.plan.source_messages
        )
        prompt = (
            "You maintain durable conversation memory. Summarize only the transcript below. "
            "Preserve user statements, identities, event order, promises, negations, unresolved "
            "questions, and confirmed facts. Do not invent details. Use concise plain text; "
            "do not output JSON.\n\nTRANSCRIPT\n" + transcript
        )
        result = await self._text_generation_service.generate_text(
            LLMTypes.GenerateTextCommand(
                request_json=prompt,
                model=command.model,
                provider=command.provider,
                max_output_tokens=command.max_output_tokens,
            )
        )
        if result.status not in {None, "completed", "succeeded"}:
            raise ValueError("Summary provider returned an incomplete result.")
        content = result.content.strip()
        if not content:
            raise ValueError("Summary provider returned empty text.")
        return Types.GeneratedSummaryInfo(
            plan=command.plan,
            content=content,
            provider=result.provider,
            model=result.model,
            input_tokens=result.usage.input_tokens,
            output_tokens=result.usage.output_tokens,
        )


# 검증된 요약을 임베딩 전 pending 상태로 저장한다. 동일 출처 범위·리비전·프롬프트 버전은 기존 행을 재사용한다.
async def save_summary(session, command: Types.SaveSummaryCommand) -> Types.MemoryInfo:
    if not 0 <= command.importance <= 1:
        raise ValueError("Memory importance must be between 0 and 1.")
    row = await Repository.create_summary(
        session, generated=command.generated, importance=command.importance
    )
    info = PersistenceMapper.memory_entity_to_info(row)
    assert info is not None
    return info
