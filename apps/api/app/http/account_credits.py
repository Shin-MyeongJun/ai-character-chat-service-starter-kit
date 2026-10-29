"""Read-only owner credit balance and ledger; no purchases or wallet mutations."""

from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.http.contracts import account_credits as Schemas
from app.http.dependencies import Owner, Session, errors
from app.http.mapper import account_credits as SchemaMapper
from app.modules.commerce.billing import types as BillingTypes
from app.modules.commerce.billing.service import credits as BillingCredits
from app.modules.commerce.credit.service import query as CreditQueryService

router = APIRouter(prefix="/account", tags=["account"])


@router.get("/overview-counts", response_model=None)
async def read_counts(session: Session, owner: Owner) -> dict[str, int]:
    """Bind overview totals to authenticated ownership rather than client array lengths."""
    from app.use_cases.account_overview import (
        GetAccountCountsCommand,
        get_account_counts,
    )

    with errors():
        return await get_account_counts(session, GetAccountCountsCommand(owner))


class CreditBalanceDto(BaseModel):
    balance_credit: int
    reserved_credit: int
    available_credit: int


@router.get("/credits/transactions", response_model=Schemas.CreditHistoryResponseDto)
async def list_credit_transactions(
    session: Session,
    owner: Owner,
    request: Annotated[Schemas.CreditHistoryRequestDto, Query()],
) -> Schemas.CreditHistoryResponseDto:
    with errors():
        info = await CreditQueryService.list_credit_transactions(
            session, SchemaMapper.credit_history_request_to_command(request, owner)
        )
        return SchemaMapper.credit_history_info_to_response(info)


@router.get("/credits", response_model=CreditBalanceDto)
async def read_credits(session: Session, owner: Owner) -> CreditBalanceDto:
    with errors():
        info = await BillingCredits.get_credit_balance(
            session, BillingTypes.GetCreditBalanceCommand(user_id=owner)
        )
        return CreditBalanceDto(
            balance_credit=info.balance_credit,
            reserved_credit=info.reserved_credit,
            available_credit=info.available_credit,
        )
