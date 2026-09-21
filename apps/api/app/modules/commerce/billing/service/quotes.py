"""Server-only quote lifecycle. Caller supplies authenticated, resolved execution."""

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.idempotency import lock_key
from app.db.transaction import use_case_transaction
from app.modules.commerce.billing import repository as Repository
from app.modules.commerce.billing import types as Types
from app.modules.commerce.billing.mapper import quotes as QuotePersistenceMapper
from app.modules.commerce.billing.service import pricing as PricingService


def _get_utc_now() -> datetime:
    return datetime.now(UTC)


def _get_quote_time(clock: Callable[[], datetime]) -> datetime:
    now = clock()
    if now.tzinfo is None or now.utcoffset() is None:
        raise Types.BillingPricingError(
            "Quote clock must return timezone-aware datetime."
        )
    return now


def _validate_quote_request(
    info: Types.BillingQuoteInfo, request: Types.BillingRequestInfo
) -> None:
    if info.request != request:
        raise Types.BillingQuoteConflictError(
            "Quote belongs to different request or execution conditions."
        )


def _resolve_quote_status(
    info: Types.BillingQuoteInfo, now: datetime
) -> Types.BillingQuoteInfo:
    return replace(
        info,
        status=(
            Types.BillingQuoteStatus.EXPIRED
            if now >= info.expires_at
            else Types.BillingQuoteStatus.QUOTED
        ),
    )


async def create_billing_quote(
    session: AsyncSession,
    command: Types.CreateBillingQuoteCommand,
    *,
    configuration: PricingService.BillingPricingConfiguration,
    clock: Callable[[], datetime] = _get_utc_now,
) -> Types.BillingQuoteInfo:
    PricingService._validate_request(command.request)
    request = command.request
    async with use_case_transaction(session):
        await lock_key(
            session, "billing-quote", f"{request.user_id}:{request.request_key}"
        )
        row = await Repository.get_billing_quote_by_key(
            session, request.user_id, request.request_key
        )
        existing = QuotePersistenceMapper.quote_entity_to_info(row)
        if existing is not None:
            _validate_quote_request(existing, request)
            # Retries never recalculate or extend expiry, including expired quotes.
            return _resolve_quote_status(existing, _get_quote_time(clock))
        price = PricingService.calculate_billing_price(
            Types.CalculateBillingPriceCommand(request=request),
            configuration=configuration,
        )
        now = _get_quote_time(clock)
        info = Types.BillingQuoteInfo(
            id=uuid4(),
            request=request,
            price=price,
            status=Types.BillingQuoteStatus.QUOTED,
            expires_at=now + timedelta(seconds=configuration.quote_ttl_seconds),
        )
        request_snapshot, price_snapshot = (
            QuotePersistenceMapper.quote_info_to_snapshots(info)
        )
        row = await Repository.create_billing_quote(
            session,
            quote_id=info.id,
            user_id=request.user_id,
            request_key=request.request_key,
            request_snapshot=request_snapshot,
            price_snapshot=price_snapshot,
            created_at=now,
            expires_at=info.expires_at,
        )
        return QuotePersistenceMapper.quote_entity_to_info(row)


async def get_billing_quote(
    session: AsyncSession,
    command: Types.GetBillingQuoteCommand,
    *,
    clock: Callable[[], datetime] = _get_utc_now,
) -> Types.BillingQuoteInfo:
    PricingService._validate_request(command.request)
    if not isinstance(command.quote_id, UUID):
        raise Types.BillingPricingError("Quote ID must be UUID.")
    row = await Repository.get_billing_quote(
        session, command.request.user_id, command.quote_id
    )
    info = QuotePersistenceMapper.quote_entity_to_info(row)
    if info is None:
        raise Types.BillingQuoteNotFoundError("Billing quote not found for this user.")
    _validate_quote_request(info, command.request)
    return _resolve_quote_status(info, _get_quote_time(clock))


async def validate_billing_quote(
    session: AsyncSession,
    command: Types.GetBillingQuoteCommand,
    *,
    clock: Callable[[], datetime] = _get_utc_now,
) -> Types.BillingQuoteInfo:
    """Future reservation entry point: match every condition and reject expiry."""
    info = await get_billing_quote(session, command, clock=clock)
    if info.status is Types.BillingQuoteStatus.EXPIRED:
        raise Types.BillingQuoteExpiredError(
            "Billing quote expired; a new request key is required."
        )
    return info
