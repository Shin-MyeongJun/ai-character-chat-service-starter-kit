"""Pure conversion of chat prompt rows to detached public values."""

from collections.abc import Iterable
from typing import overload

from app.db.models.generation_prompt import GenerationPrompt
from app.modules.chatting.chat import repository as Repository
from app.modules.chatting.chat import types as Types


@overload
def prompt_entity_to_info(entity: GenerationPrompt) -> Types.GenerationPromptInfo: ...


@overload
def prompt_entity_to_info(entity: None) -> None: ...


def prompt_entity_to_info(
    entity: GenerationPrompt | None,
) -> Types.GenerationPromptInfo | None:
    if entity is None:
        return None
    return Types.GenerationPromptInfo(
        request_json=entity.request_json,
        digest=entity.digest,
        format_version=entity.format_version,
        created_at=entity.created_at,
        provider=entity.provider,
        max_output_tokens=entity.max_output_tokens,
    )


@overload
def generation_prompt_row_to_summary(
    row: Repository.GenerationPromptSummaryRow,
) -> Types.GenerationPromptSummaryInfo: ...


@overload
def generation_prompt_row_to_summary(row: None) -> None: ...


def generation_prompt_row_to_summary(
    row: Repository.GenerationPromptSummaryRow | None,
) -> Types.GenerationPromptSummaryInfo | None:
    if row is None:
        return None
    (
        generation_id,
        conversation_id,
        model_id,
        model_name,
        reasoning_effort,
        status,
        created_at,
        finished_at,
        history_invalidated_at,
        prompt_recorded,
        prompt_created_at,
        provider,
    ) = row._tuple()
    return Types.GenerationPromptSummaryInfo(
        generation_id=generation_id,
        conversation_id=conversation_id,
        model_id=model_id,
        model_name=model_name,
        reasoning_effort=reasoning_effort,
        status=status,
        created_at=created_at,
        finished_at=finished_at,
        history_invalidated_at=history_invalidated_at,
        prompt_recorded=prompt_recorded,
        prompt_created_at=prompt_created_at,
        provider=provider,
    )


def generation_prompt_rows_to_page(
    rows: Iterable[Repository.GenerationPromptSummaryRow], total: int
) -> Types.GenerationPromptPageInfo:
    return Types.GenerationPromptPageInfo(
        tuple(generation_prompt_row_to_summary(row) for row in rows), total
    )
