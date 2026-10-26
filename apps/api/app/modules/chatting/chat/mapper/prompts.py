"""Pure conversion of chat prompt rows to detached public values."""

from app.modules.chatting.chat import types as Types


def prompt_entity_to_info(entity) -> Types.GenerationPromptInfo | None:
    if entity is None:
        return None
    return Types.GenerationPromptInfo(
        **{
            key: getattr(entity, key)
            for key in Types.GenerationPromptInfo.__dataclass_fields__
        }
    )


def generation_prompt_row_to_summary(row) -> Types.GenerationPromptSummaryInfo | None:
    if row is None:
        return None
    return Types.GenerationPromptSummaryInfo(
        **{
            key: getattr(row, key)
            for key in Types.GenerationPromptSummaryInfo.__dataclass_fields__
        }
    )


def generation_prompt_rows_to_page(rows, total) -> Types.GenerationPromptPageInfo:
    return Types.GenerationPromptPageInfo(
        tuple(generation_prompt_row_to_summary(row) for row in rows), total
    )
