# 저장된 사용자 메시지를 참조해 답변 하나를 요청한다. 중복 키 처리·복구는
# AnswerOrchestrator가 맡는다.
# pending은 202와 Retry-After, 저장 복구 대기는 503으로 구분한다.
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response

from app.http.dependencies import Owner
from app.modules.chatting.chat.dependencies import get_answer_orchestrator
from app.modules.chatting.chat.mapper.schema import answers as SchemaMapper
from app.modules.chatting.chat.schemas import answers as Schemas
from app.modules.chatting.chat.service.workflow.answers import AnswerOrchestrator
from app.modules.chatting.chat.types import AnswerStorageError, MessageConflictError
from app.modules.commerce.billing import types as BillingTypes

router = APIRouter()


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
    except BillingTypes.InsufficientCreditError as exc:
        raise HTTPException(402, {"code": "insufficient_credit"}) from exc
    except BillingTypes.CreditAccountNotFoundError as exc:
        raise HTTPException(409, {"code": "credit_account_unavailable"}) from exc
    except BillingTypes.BillingPricingError as exc:
        raise HTTPException(503, {"code": "billing_not_configured"}) from exc
    except (
        BillingTypes.BillingQuoteConflictError,
        BillingTypes.BillingQuoteExpiredError,
        BillingTypes.CreditReservationConflictError,
    ) as exc:
        raise HTTPException(409, {"code": "billing_conflict"}) from exc
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
