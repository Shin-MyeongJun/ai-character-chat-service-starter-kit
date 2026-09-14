"""Assemble existing runtime settings, recent raw history, and selected memories."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from uuid import UUID

from app.modules.chatting.chat import service as ChatService
from app.modules.chatting.chat import types as ChatTypes
from app.modules.chatting.conversation import service as ConversationService
from app.modules.chatting.conversation import types as ConversationTypes
from app.modules.chatting.memory import service as MemoryService
from app.modules.chatting.memory import types as MemoryTypes
from app.modules.llm import types as LLMTypes


@dataclass(frozen=True, slots=True, kw_only=True)
class PrepareAnswerContextCommand:
    conversation_id: UUID
    owner_id: UUID
    current_message: str
    max_prompt_tokens: int
    response_tokens: int
    embedding_model: str
    embedding_provider: LLMTypes.EmbeddingProvider | str | None = None
    embedding_output_dimension: int | None = None
    policy: MemoryTypes.MemoryPolicy = field(default_factory=MemoryTypes.MemoryPolicy)
    current_message_id: UUID | None = None
    runtime: ConversationTypes.ConversationRuntimeView | None = None
    rendered_base_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class PromptBudgetInfo:
    maximum: int
    base: int
    memories: int
    recent_messages: int
    current_message: int
    response_reserve: int


@dataclass(frozen=True, slots=True)
class AnswerContextInfo:
    runtime: ConversationTypes.ConversationRuntimeView
    memories: tuple[MemoryTypes.RetrievedMemoryInfo, ...]
    recent_messages: tuple[ChatTypes.MessageInfo, ...]
    current_message: str
    budget: PromptBudgetInfo
    memory_state: str


async def prepare_answer_context(
    session_factory,
    command: PrepareAnswerContextCommand,
    *,
    memory_retriever: MemoryService.MemoryRetriever,
) -> AnswerContextInfo:
    if (
        not command.current_message.strip()
        or command.max_prompt_tokens < 1
        or command.response_tokens < 1
        or command.response_tokens >= command.max_prompt_tokens
    ):
        raise ValueError("Invalid answer context request or token budget.")
    if (
        not 1 <= command.policy.retrieval_candidates <= 100
        or not 1
        <= command.policy.retrieval_limit
        <= command.policy.retrieval_candidates
    ):
        raise ValueError(
            "Memory retrieval limit/candidates must satisfy 1 <= limit <= candidates <= 100."
        )
    runtime = command.runtime
    if runtime is None:
        async with session_factory() as session:
            runtime = await ConversationService.prepare_runtime_context(
                session,
                ConversationTypes.PrepareRuntimeContextCommand(
                    conversation_id=command.conversation_id,
                    user_id=command.owner_id,
                    activation_text=command.current_message,
                ),
            )
    async with session_factory() as session:
        latest = await MemoryService.get_latest_summary(
            session,
            MemoryTypes.GetLatestSummaryCommand(
                conversation_id=command.conversation_id, owner_id=command.owner_id
            ),
        )
        source = await ChatService.list_memory_source(
            session,
            ChatTypes.ListMemorySourceCommand(
                conversation_id=command.conversation_id, user_id=command.owner_id
            ),
        )
    if source.truncated:
        raise MemoryTypes.ContextBudgetExceededError(
            "Conversation history exceeds the safe prompt inspection limit.",
            summary_required=True,
        )
    base_tokens = (
        command.rendered_base_tokens
        if command.rendered_base_tokens is not None
        else MemoryService.estimate_tokens(
            json.dumps(asdict(runtime), ensure_ascii=False, default=str)
        )
    )
    current_is_saved = bool(
        source.messages
        and source.messages[-1].sender_type == "user"
        and source.messages[-1].id == command.current_message_id
    )
    current_tokens = (
        0
        if current_is_saved
        else MemoryService.estimate_tokens(f"user: {command.current_message}\n")
    )
    fixed = base_tokens + command.response_tokens + current_tokens
    if fixed >= command.max_prompt_tokens:
        raise MemoryTypes.ContextBudgetExceededError(
            "Runtime settings and response reserve exceed the prompt window.",
            summary_required=False,
        )
    summary_end = (
        latest.source_end_position if latest and latest.source_end_position else 0
    )
    # The current input is reserved in the rendered base for orchestration and
    # must never become optional summarized history.
    if command.rendered_base_tokens is not None:
        source = ChatTypes.MemorySourceInfo(
            tuple(
                item
                for item in source.messages
                if item.id != command.current_message_id
            ),
            source.truncated,
        )
    unprocessed = tuple(item for item in source.messages if item.position > summary_end)
    message_tokens = (
        _rendered_message_tokens
        if command.rendered_base_tokens is not None
        else _message_tokens
    )
    unprocessed_tokens = sum(message_tokens(item) for item in unprocessed)
    available = command.max_prompt_tokens - fixed
    if unprocessed_tokens > available:
        raise MemoryTypes.ContextBudgetExceededError(
            "Unsummarized messages do not fit; wait for memory summarization and retry.",
            summary_required=True,
        )

    processed = [item for item in source.messages if item.position <= summary_end]
    recent_processed: list[ChatTypes.MessageInfo] = []
    reserved_raw_tokens = 0
    recent_target = min(
        command.policy.recent_raw_tokens, available - unprocessed_tokens
    )
    for item in reversed(processed):
        tokens = message_tokens(item)
        if reserved_raw_tokens + tokens > recent_target:
            break
        recent_processed.append(item)
        reserved_raw_tokens += tokens

    remaining_after_recent = available - unprocessed_tokens - reserved_raw_tokens
    memory_budget = min(command.policy.memory_token_budget, remaining_after_recent)
    fallback: list[MemoryTypes.RetrievedMemoryInfo] = []
    memory_state = "ready"
    if latest is not None and latest.index_status != "ready":
        memory_state = "index_pending"
        fallback_tokens = (
            MemoryService.estimate_rendered_memory_tokens(latest.content)
            if command.rendered_base_tokens is not None
            else MemoryService.estimate_tokens(latest.content)
        )
        if fallback_tokens > memory_budget:
            raise MemoryTypes.ContextBudgetExceededError(
                "The pending summary does not fit in the configured memory budget.",
                summary_required=False,
            )
        fallback.append(
            MemoryTypes.RetrievedMemoryInfo(
                memory_id=latest.id,
                memory_type=latest.memory_type,
                content=latest.content,
                similarity_score=0.0,
                importance=latest.importance,
                selection_score=latest.importance,
                estimated_tokens=fallback_tokens,
                source_start_position=latest.source_start_position,
                source_end_position=latest.source_end_position,
                source_digest=latest.source_digest,
                conversation_revision=latest.conversation_revision,
                summary_provider=latest.summary_provider,
                summary_model=latest.summary_model,
                prompt_version=latest.prompt_version,
                created_at=latest.created_at,
            )
        )
    elif (
        latest is None
        and unprocessed_tokens >= command.policy.summarization_threshold_tokens
    ):
        memory_state = "summary_pending"

    fallback_tokens = sum(item.estimated_tokens for item in fallback)
    query_parts = [
        f"{item.sender_type}: {item.content}" for item in source.messages[-6:]
    ]
    if not current_is_saved or command.rendered_base_tokens is not None:
        query_parts.append(f"user: {command.current_message}")
    query_text = "\n".join(query_parts)
    retrieval_limit = command.policy.retrieval_limit - len(fallback)
    retrieval_budget = memory_budget - fallback_tokens
    retrieved = []
    if retrieval_limit and retrieval_budget:
        retrieved = await memory_retriever.retrieve_memories(
            MemoryTypes.SearchMemoriesCommand(
                conversation_id=command.conversation_id,
                query_text=query_text,
                owner_id=command.owner_id,
                top_k=command.policy.retrieval_candidates,
                embedding_model=command.embedding_model,
                embedding_provider=command.embedding_provider,
                output_dimension=command.embedding_output_dimension,
                token_budget=retrieval_budget,
                result_limit=retrieval_limit,
                conservative_token_budget=command.rendered_base_tokens is not None,
            )
        )
    memories = fallback + [
        item
        for item in retrieved
        if not fallback or item.memory_id != fallback[0].memory_id
    ]
    memories = memories[: command.policy.retrieval_limit]
    memory_tokens = sum(item.estimated_tokens for item in memories)
    raw_budget = max(0, available - unprocessed_tokens - memory_tokens)
    used_raw = reserved_raw_tokens
    already_selected = {item.id for item in recent_processed}
    for item in reversed(processed):
        if item.id in already_selected:
            continue
        tokens = message_tokens(item)
        if used_raw + tokens > raw_budget:
            break
        recent_processed.append(item)
        used_raw += tokens
    recent_messages = tuple(reversed(recent_processed)) + unprocessed
    recent_tokens = used_raw + unprocessed_tokens
    return AnswerContextInfo(
        runtime=runtime,
        memories=tuple(memories),
        recent_messages=recent_messages,
        current_message=command.current_message,
        budget=PromptBudgetInfo(
            maximum=command.max_prompt_tokens,
            base=base_tokens,
            memories=memory_tokens,
            recent_messages=recent_tokens,
            current_message=current_tokens,
            response_reserve=command.response_tokens,
        ),
        memory_state=memory_state,
    )


def _message_tokens(item: ChatTypes.MessageInfo) -> int:
    return MemoryService.estimate_tokens(f"{item.sender_type}: {item.content}\n")


def _rendered_message_tokens(item: ChatTypes.MessageInfo) -> int:
    return len(item.content.encode()) + 32
