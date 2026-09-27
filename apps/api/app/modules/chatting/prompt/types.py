from __future__ import annotations

# TemplateInfo.digest는 템플릿 내용 식별값이다. PromptInfo.request_json은 공급자 중립 역할 envelope다.
from dataclasses import dataclass
from uuid import UUID

from app.modules.chatting.conversation.types import ConversationRuntimeView
from app.modules.chatting.memory.types import RetrievedMemoryInfo


class TemplateConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class TemplateInfo:
    template_id: str
    version: int
    digest: str
    role_rules: tuple[str, ...]
    expression_rules: tuple[str, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class BuildPromptCommand:
    template: TemplateInfo
    runtime: ConversationRuntimeView
    product_character_id: UUID
    current_message: PromptMessageInfo
    recent_messages: tuple[PromptMessageInfo, ...] = ()
    memories: tuple[RetrievedMemoryInfo, ...] = ()


@dataclass(frozen=True, slots=True)
class PromptInfo:
    request_json: str
    estimated_tokens: int


@dataclass(frozen=True, slots=True)
class PromptMessageInfo:
    id: UUID
    sender_type: str
    content: str
    position: int
