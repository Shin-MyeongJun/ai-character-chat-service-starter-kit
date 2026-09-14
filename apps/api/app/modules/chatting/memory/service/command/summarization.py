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


async def save_summary(session, command: Types.SaveSummaryCommand) -> Types.MemoryInfo:
    if not 0 <= command.importance <= 1:
        raise ValueError("Memory importance must be between 0 and 1.")
    row = await Repository.create_summary(
        session, generated=command.generated, importance=command.importance
    )
    info = PersistenceMapper.memory_entity_to_info(row)
    assert info is not None
    return info
