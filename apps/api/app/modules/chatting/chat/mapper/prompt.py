"""Pure conversion of chat history into prompt-owned input values."""

from app.modules.chatting.chat import types as Types
from app.modules.chatting.prompt import types as PromptTypes


def message_info_to_prompt(value: Types.MessageInfo) -> PromptTypes.PromptMessageInfo:
    return PromptTypes.PromptMessageInfo(
        value.id, value.sender_type, value.content, value.position
    )
