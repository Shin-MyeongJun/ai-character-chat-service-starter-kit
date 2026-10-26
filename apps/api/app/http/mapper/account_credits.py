"""Translate public credit values without exposing private metadata or executing I/O."""

from uuid import UUID

from app.http.contracts import account_credits as Schemas
from app.modules.commerce.credit import types as CreditTypes


def credit_history_request_to_command(
    request: Schemas.CreditHistoryRequestDto, owner_id: UUID
) -> CreditTypes.ListCreditTransactionsCommand:
    """Bind identity and CREDIT scope independently of caller-provided filters."""
    return CreditTypes.ListCreditTransactionsCommand(
        user_id=owner_id,
        currency_code="CREDIT",
        start=request.start,
        end=request.end,
        limit=request.limit,
        direction=request.direction,
        cursor=CreditTypes.CreditCursor(
            created_at=request.cursor_created_at, id=request.cursor_id
        )
        if request.cursor_id is not None
        else None,
    )


def credit_history_info_to_response(
    info: CreditTypes.CreditTransactionPageInfo,
) -> Schemas.CreditHistoryResponseDto:
    return Schemas.CreditHistoryResponseDto(
        items=[
            Schemas.CreditTransactionResponseDto(
                id=item.id,
                operation=item.operation,
                amount=item.amount,
                free_amount=item.free_amount,
                paid_amount=item.paid_amount,
                created_at=item.created_at,
            )
            for item in info.items
        ],
        next_cursor_created_at=info.next_cursor.created_at
        if info.next_cursor
        else None,
        next_cursor_id=info.next_cursor.id if info.next_cursor else None,
    )
