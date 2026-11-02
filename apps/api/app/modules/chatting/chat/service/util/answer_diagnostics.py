"""Bounded diagnostics without exception messages, SQL, source text or locals."""

from pathlib import Path
from typing import TypedDict

from sqlalchemy.exc import DataError, DBAPIError, IntegrityError, SQLAlchemyError
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError

from app.modules.chatting.chat import types as Types
from app.modules.chatting.memory import types as MemoryTypes
from app.modules.commerce.billing import types as BillingTypes
from app.modules.llm import types as LLMTypes

APPLICATION_ROOT = Path(__file__).resolve().parents[5]


class AnswerErrorDetails(TypedDict):
    error_kind: str
    failure_class: str
    exception_chain: list[str]
    stack_frames: list[dict[str, str | int]]


def _failure_class(error: Exception) -> str:
    for _ in range(4):
        if (
            isinstance(error, Types.AnswerStorageError)
            and not isinstance(error, Types.AnswerStateError)
            and isinstance(error.__cause__, Exception)
        ):
            error = error.__cause__
        else:
            break
    if isinstance(error, Types.AnswerStateError):
        return "invariant"
    if isinstance(error, Types.AnswerStorageError):
        return "storage_uncertain"
    if isinstance(error, (IntegrityError, DataError)):
        return "storage_constraint"
    if isinstance(error, SQLAlchemyTimeoutError) or (
        isinstance(error, DBAPIError) and error.connection_invalidated
    ):
        return "storage_unavailable"
    if isinstance(error, SQLAlchemyError):
        # OperationalError alone does not prove a transient failure.
        return "storage_error"
    if isinstance(error, (LLMTypes.LLMError, LLMTypes.EmbeddingError)):
        return "provider_retryable" if error.retryable else "provider_permanent"
    if isinstance(error, TimeoutError):
        return "timeout"
    if isinstance(
        error,
        (
            MemoryTypes.ContextBudgetExceededError,
            LLMTypes.UnsupportedModelError,
            LLMTypes.UnsupportedReasoningEffortError,
            LLMTypes.UnsupportedEmbeddingModelError,
            BillingTypes.CreditReservationConflictError,
            BillingTypes.CreditReservationNotFoundError,
        ),
    ):
        return "domain"
    return "internal"


def error_details(error: Exception) -> AnswerErrorDetails:
    """Describe causes by type and application code location, never by repr/str."""
    chain: list[str] = []
    stack: list[dict[str, str | int]] = []
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen and len(chain) < 4:
        seen.add(id(current))
        chain.append(type(current).__name__)
        traceback = current.__traceback__
        while traceback is not None:
            code = traceback.tb_frame.f_code
            try:
                filename = (
                    Path(code.co_filename).resolve().relative_to(APPLICATION_ROOT)
                )
            except ValueError:
                pass
            else:
                stack.append(
                    {
                        "file": filename.as_posix(),
                        "function": code.co_name,
                        "line": traceback.tb_lineno,
                    }
                )
                stack = stack[-24:]
            traceback = traceback.tb_next
        current = current.__cause__ or (
            None if current.__suppress_context__ else current.__context__
        )
    return {
        "error_kind": type(error).__name__,
        "failure_class": _failure_class(error),
        "exception_chain": chain,
        "stack_frames": stack,
    }
