"""Synthetic credit setup; these grants do not represent cash payments."""

from uuid import uuid4

from app.modules.commerce.credit import types as CreditTypes
from app.modules.commerce.credit.service import command as CreditCommandService


async def fund_credit(
    session,
    user_id,
    amount=20,
    currency_code="CREDIT",
    bucket=CreditTypes.CreditBucket.FREE,
):
    if amount == 0:
        return await CreditCommandService.prepare_credit_wallet(
            session,
            CreditTypes.PrepareCreditWalletCommand(
                user_id=user_id,
                currency_code=currency_code,
            ),
        )
    return await CreditCommandService.grant_credit(
        session,
        CreditTypes.GrantCreditCommand(
            user_id=user_id,
            currency_code=currency_code,
            bucket=bucket,
            amount=amount,
            reason="purchase",
            reference_id=uuid4(),
            namespace="fixture",
            request_key=uuid4(),
        ),
    )
