"""Read-only public credit queries, with no product or quote interpretation."""

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.commerce.credit import repository as Repository
from app.modules.commerce.credit import types as Types
from app.modules.commerce.credit.mapper import persistence as PersistenceMapper
from app.modules.commerce.credit.service import command as CommandService


async def get_credit_balance(
    session: AsyncSession, command: Types.GetCreditBalanceCommand
) -> Types.CreditBalanceInfo:
    CommandService._validate_identifiers(command.user_id)
    return await CommandService._get_credit_balance(
        session, command.user_id, command.currency_code, for_update=False
    )


async def get_credit_reservation(
    session: AsyncSession, command: Types.GetCreditReservationCommand
) -> Types.CreditReservationInfo | None:
    CommandService._validate_identifiers(command.user_id, command.request_key)
    CommandService._validate_metadata(command.namespace)
    CommandService._validate_currency(command.currency_code)
    row = await Repository.get_credit_reservation_by_key(
        session,
        command.user_id,
        command.namespace,
        command.request_key,
        command.currency_code,
        for_update=False,
    )
    return PersistenceMapper.credit_reservation_entity_to_info(row)


def _validate_history_command(command: Types.ListCreditTransactionsCommand) -> dict:
    CommandService._validate_identifiers(command.user_id)
    if command.currency_code is not None:
        CommandService._validate_currency(command.currency_code)
    for value in (command.namespace, command.reason):
        if value is not None:
            CommandService._validate_metadata(value)
    if type(command.limit) is not int or not 1 <= command.limit <= 100:
        raise Types.InvalidCreditCommandError("Page limit must be 1..100.")
    if command.cursor is not None and not isinstance(
        command.cursor, Types.CreditCursor
    ):
        raise Types.InvalidCreditCommandError("Invalid history cursor.")
    for timestamp in (
        command.start,
        command.end,
        command.cursor.created_at if command.cursor else None,
    ):
        if timestamp is not None and (
            not isinstance(timestamp, datetime) or timestamp.utcoffset() is None
        ):
            raise Types.InvalidCreditCommandError(
                "History times must be timezone-aware."
            )
    if (
        command.start is not None
        and command.end is not None
        and command.start >= command.end
    ):
        raise Types.InvalidCreditCommandError("History range must be non-empty.")
    if command.cursor is not None:
        CommandService._validate_identifiers(command.cursor.id)
    return dict(
        user_id=command.user_id,
        currency_code=command.currency_code,
        namespace=command.namespace,
        reason=command.reason,
        start=command.start,
        end=command.end,
        limit=command.limit,
        cursor=(command.cursor.created_at, command.cursor.id)
        if command.cursor
        else None,
    )


async def list_credit_transactions(
    session: AsyncSession, command: Types.ListCreditTransactionsCommand
) -> Types.CreditTransactionPageInfo:
    rows = await Repository.list_credit_transactions(
        session, **_validate_history_command(command)
    )
    infos = tuple(PersistenceMapper.credit_transaction_row_to_info(row) for row in rows)
    items = tuple(info for info in infos[: command.limit] if info is not None)
    cursor = (
        Types.CreditCursor(created_at=items[-1].created_at, id=items[-1].id)
        if len(infos) > command.limit
        else None
    )
    return Types.CreditTransactionPageInfo(items=items, next_cursor=cursor)


async def list_credit_reservations(
    session: AsyncSession, command: Types.ListCreditReservationsCommand
) -> Types.CreditReservationPageInfo:
    filters = _validate_history_command(command)
    if command.status is not None and not isinstance(
        command.status, Types.CreditReservationStatus
    ):
        raise Types.InvalidCreditCommandError("Invalid reservation status.")
    rows = await Repository.list_credit_reservations(
        session, **filters, status=command.status
    )
    infos = tuple(
        PersistenceMapper.credit_reservation_entity_to_info(row) for row in rows
    )
    items = tuple(info for info in infos[: command.limit] if info is not None)
    cursor = (
        Types.CreditCursor(created_at=items[-1].created_at, id=items[-1].id)
        if len(infos) > command.limit
        else None
    )
    return Types.CreditReservationPageInfo(items=items, next_cursor=cursor)
