from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.http import answer_mapper as SchemaMapper
from app.http.contracts import answers as Schemas
from app.http.dependencies import Owner
from app.modules.chatting.chat.types import MessageConflictError
from app.use_cases.answers import AnswerOrchestrator, AnswerStorageError

router = APIRouter()


def get_answer_orchestrator(request: Request) -> AnswerOrchestrator:
    value = getattr(request.app.state, "answer_orchestrator", None)
    if value is None:
        raise HTTPException(503, "Answer runtime is not configured.")
    return value


@router.post(
    "/conversations/{conversation_id}/answers",
    response_model=Schemas.GenerateAnswerResponseDto,
)
async def generate_answer(
    conversation_id: UUID,
    value: Schemas.GenerateAnswerRequestDto,
    owner_id: Owner,
    response: Response,
    orchestrator: Annotated[AnswerOrchestrator, Depends(get_answer_orchestrator)],
) -> Schemas.GenerateAnswerResponseDto:
    try:
        result = await orchestrator.generate_answer(
            SchemaMapper.answer_request_to_command(value, conversation_id, owner_id)
        )
    except LookupError as exc:
        raise HTTPException(404, "Conversation or input not found.") from exc
    except MessageConflictError as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except AnswerStorageError as exc:
        raise HTTPException(
            503, {"code": "storage_pending_recovery", "retry_same_key": True}
        ) from exc
    if result.status == "pending":
        response.status_code = 202
        response.headers["Retry-After"] = "3"
    elif result.status != "succeeded":
        response.status_code = _failure_status(result.error_code)
    return SchemaMapper.answer_info_to_response(result)


def _failure_status(code):
    if code in ("summary_required", "stale", "cancelled", "interrupted_before_call"):
        return 409
    if code in ("fixed_context_exceeded", "unsupported_model"):
        return 422
    if code == "llm_rate_limit":
        return 429
    if code in ("llm_timeout", "timeout"):
        return 504
    return 502
