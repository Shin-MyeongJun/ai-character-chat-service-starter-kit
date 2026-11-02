"""Internal SDK boundaries, preserving injected clients and raw response values."""

from collections.abc import Iterable
from typing import NotRequired, Protocol, TypedDict, cast


class OpenAIRequest(TypedDict):
    model: str
    input: str | list[dict[str, str]]
    max_output_tokens: int
    store: bool
    reasoning: NotRequired[dict[str, str]]


class AnthropicRequest(TypedDict):
    model: str
    max_tokens: int
    messages: list[dict[str, str]]
    system: NotRequired[str]
    output_config: NotRequired[dict[str, str]]


class AsyncCreateResource(Protocol):
    async def create(self, **params: object) -> object: ...


class ResponsesClient(Protocol):
    @property
    def responses(self) -> AsyncCreateResource: ...


class MessagesClient(Protocol):
    @property
    def messages(self) -> AsyncCreateResource: ...


class VoyageClient(Protocol):
    async def embed(
        self,
        texts: list[str],
        *,
        model: str,
        input_type: str,
        truncation: bool,
        output_dtype: str,
        output_dimension: int | None,
    ) -> object: ...


def response_attribute(
    value: object | None, name: str, default: object = None
) -> object:
    if value is None:
        return default
    if isinstance(value, dict):
        result: object = value.get(name, default)
        return result
    result = getattr(value, name, default)
    return result


# The SDK field contracts, also represented by dict/SimpleNamespace test clients,
# supply these types. These projections deliberately do not coerce, filter or
# validate malformed values: existing downstream behavior remains observable.
def string_attribute(
    value: object | None, name: str, default: str | None = None
) -> str | None:
    return cast(str | None, response_attribute(value, name, default))


def integer_attribute(value: object | None, name: str) -> int | None:
    return cast(int | None, response_attribute(value, name))


def sequence_attribute(
    value: object | None, name: str, default: Iterable[object] = ()
) -> Iterable[object] | None:
    return cast(Iterable[object] | None, response_attribute(value, name, default))
