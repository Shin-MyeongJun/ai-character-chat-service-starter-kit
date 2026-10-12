"""Read-only owner credit balance for the chat UI."""

from fastapi import APIRouter
from pydantic import BaseModel

from app.http.dependencies import Owner, Session, errors
from app.modules.commerce.billing import types as BillingTypes
from app.modules.commerce.billing.service import credits as BillingCredits

router = APIRouter(prefix="/account", tags=["account"])


class CreditBalanceDto(BaseModel):
    balance_credit: int
    reserved_credit: int
    available_credit: int


@router.get("/credits", response_model=CreditBalanceDto)
async def read_credits(session: Session, owner: Owner):
    with errors():
        info = await BillingCredits.get_credit_balance(
            session, BillingTypes.GetCreditBalanceCommand(user_id=owner)
        )
        return CreditBalanceDto(
            balance_credit=info.balance_credit,
            reserved_credit=info.reserved_credit,
            available_credit=info.available_credit,
        )
