"""Public billing composition on PostgreSQL; no chat/LLM result persistence.

Users and opening balances are fixture data. ORM reads below audit durable billing
state only; every business operation goes through public service/Command contracts.
"""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from app.db.models.billing_credit import CreditReservation
from app.db.models.billing_quote import BillingQuote
from app.db.models.credit import CreditTransaction
from app.db.models.identity import User
from app.db.transaction import use_case_transaction
from app.modules.commerce.billing import types as BillingTypes
from app.modules.commerce.billing.service import credits as BillingCreditService
from app.modules.commerce.billing.service import policies as BillingPolicyService
from app.modules.commerce.billing.service import pricing as BillingPricingService
from app.modules.commerce.billing.service import quotes as BillingQuoteService
from credit_support import fund_credit
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from test_billing_prices import (
    AdjustmentAdapter,
    _configuration,  # noqa: F401
    _request_info,  # noqa: F401
)

NOW = datetime(2026, 9, 21, tzinfo=UTC)


@pytest_asyncio.fixture
async def funded_request(
    db: AsyncSession, request_info: BillingTypes.BillingRequestInfo
) -> BillingTypes.BillingRequestInfo:
    async with use_case_transaction(db):
        assert await db.scalar(text("SELECT version()")) is not None
        assert db.bind.dialect.name == "postgresql"
        assert await db.scalar(text("SHOW transaction_isolation")) == "read committed"
        db.add(
            User(id=request_info.user_id, email=f"{request_info.user_id}@test.local")
        )
        await db.flush()
        await fund_credit(db, request_info.user_id)
    return request_info


def _reserve_command(
    quote: BillingTypes.BillingQuoteInfo,
) -> BillingTypes.ReserveCreditCommand:
    return BillingTypes.ReserveCreditCommand(
        user_id=quote.request.user_id,
        request_key=quote.request.request_key,
        quote_id=quote.id,
        request=quote.request,
    )


async def _finalize_reservation(
    session: AsyncSession,
    reservation: BillingTypes.CreditReservationInfo,
    result_id: UUID | None,
) -> BillingTypes.CreditReservationInfo:
    if result_id is not None:
        return await BillingCreditService.commit_credit_reservation(
            session,
            BillingTypes.CommitCreditReservationCommand(
                user_id=reservation.user_id,
                request_key=reservation.request_key,
                reservation_id=reservation.id,
                result_id=result_id,
            ),
        )
    return await BillingCreditService.release_credit_reservation(
        session,
        BillingTypes.ReleaseCreditReservationCommand(
            user_id=reservation.user_id,
            request_key=reservation.request_key,
            reservation_id=reservation.id,
        ),
    )


async def _assert_durable_state(
    db: AsyncSession,
    user_id: UUID,
    *,
    balance: int,
    reserved: int,
    quotes: int,
    reservations: int,
    debits: int,
) -> None:
    # A fresh connection observes committed state, not the caller's identity map.
    async with AsyncSession(db.bind) as session:
        info = await BillingCreditService.get_credit_balance(
            session, BillingTypes.GetCreditBalanceCommand(user_id=user_id)
        )
        assert info == BillingTypes.CreditBalanceInfo(
            user_id=user_id,
            balance_credit=balance,
            reserved_credit=reserved,
            available_credit=balance - reserved,
        )
        for model, expected in (
            (BillingQuote, quotes),
            (CreditReservation, reservations),
        ):
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(model)
                    .where(model.user_id == user_id)
                )
                == expected
            )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(CreditTransaction)
                .where(
                    CreditTransaction.user_id == user_id,
                    CreditTransaction.reason == "chat_usage",
                )
            )
            == debits
        )
        assert (
            await session.scalar(
                select(func.sum(CreditTransaction.amount)).where(
                    CreditTransaction.user_id == user_id
                )
            )
            == balance
        )
        assert (
            await session.scalar(
                select(
                    func.coalesce(func.sum(CreditReservation.reserved_credit), 0)
                ).where(
                    CreditReservation.user_id == user_id,
                    CreditReservation.status == "reserved",
                )
            )
            == reserved
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("succeeded", [True, False], ids=["commit", "failure-release"])
async def test_quote_reserve_finalize_and_replay_after_expiry(
    db: AsyncSession,
    funded_request: BillingTypes.BillingRequestInfo,
    configuration: BillingPricingService.BillingPricingConfiguration,
    succeeded: bool,
) -> None:
    quote = await BillingQuoteService.create_billing_quote(
        db,
        BillingTypes.CreateBillingQuoteCommand(request=funded_request),
        configuration=configuration,
        clock=lambda: NOW,
    )
    async with use_case_transaction(db):
        reservation = await BillingCreditService.reserve_credit(
            db, _reserve_command(quote), clock=lambda: NOW
        )
    await _assert_durable_state(
        db,
        funded_request.user_id,
        balance=20,
        reserved=10,
        quotes=1,
        reservations=1,
        debits=0,
    )
    # A synthetic result identifier exercises the billing contract only.
    result_id = uuid4() if succeeded else None
    async with use_case_transaction(db):
        finalized = await _finalize_reservation(db, reservation, result_id)
    assert finalized.status == (
        BillingTypes.CreditReservationStatus.COMMITTED
        if succeeded
        else BillingTypes.CreditReservationStatus.RELEASED
    )
    assert finalized.result_id == result_id
    later = NOW + timedelta(days=1)
    replay = await BillingQuoteService.create_billing_quote(
        db,
        BillingTypes.CreateBillingQuoteCommand(request=funded_request),
        configuration=replace(configuration, price_book=None),
        clock=lambda: later,
    )
    assert replay == replace(quote, status=BillingTypes.BillingQuoteStatus.EXPIRED)
    # Pre-validating expiry would wrongly reject a completed request's replay.
    async with use_case_transaction(db):
        with pytest.raises(BillingTypes.BillingQuoteExpiredError):
            await BillingQuoteService.validate_billing_quote(
                db,
                BillingTypes.GetBillingQuoteCommand(
                    quote_id=quote.id, request=funded_request
                ),
                clock=lambda: later,
            )
        assert (
            await BillingCreditService.reserve_credit(
                db, _reserve_command(replay), clock=lambda: later
            )
            == finalized
        )
        assert await _finalize_reservation(db, reservation, result_id) == finalized
    await _assert_durable_state(
        db,
        funded_request.user_id,
        balance=10 if succeeded else 20,
        reserved=0,
        quotes=1,
        reservations=1,
        debits=int(succeeded),
    )


@pytest.mark.asyncio
async def test_policy_change_only_affects_new_quote_and_settles_stored_price(
    db: AsyncSession,
    funded_request: BillingTypes.BillingRequestInfo,
    configuration: BillingPricingService.BillingPricingConfiguration,
) -> None:
    original = await BillingQuoteService.create_billing_quote(
        db,
        BillingTypes.CreateBillingQuoteCommand(request=funded_request),
        configuration=configuration,
        clock=lambda: NOW,
    )
    # Synthetic adapter exists only in tests; production promotion remains a noop.
    changed = replace(
        configuration,
        price_book=replace(configuration.price_book, version="test-only-v2"),
        policies=BillingPolicyService.PricingPolicyRegistry(
            (
                BillingPolicyService.PricingPolicyRegistration(
                    order=1,
                    adapter=AdjustmentAdapter(
                        "test-discount", multiplier=Decimal("0.5")
                    ),
                ),
            )
        ),
    )
    assert (
        await BillingQuoteService.create_billing_quote(
            db,
            BillingTypes.CreateBillingQuoteCommand(request=funded_request),
            configuration=changed,
            clock=lambda: NOW,
        )
        == original
    )
    newer = await BillingQuoteService.create_billing_quote(
        db,
        BillingTypes.CreateBillingQuoteCommand(
            request=replace(funded_request, request_key=uuid4())
        ),
        configuration=changed,
        clock=lambda: NOW,
    )
    assert original.price.final_price_credit == 10
    assert original.price.price_book_version == "test-only-v1"
    assert all(
        p.status is BillingTypes.PricingPolicyStatus.UNIMPLEMENTED
        for p in original.price.policy_results
    )
    assert newer.price.final_price_credit == 5
    assert newer.price.display_discount_percent == Decimal("50.00")
    assert newer.price.price_book_version == "test-only-v2"
    assert newer.price.policy_results[0].policy.policy_id == "test-discount"
    for quote in (original, newer):
        async with AsyncSession(db.bind) as session, use_case_transaction(session):
            stored = await BillingQuoteService.get_billing_quote(
                session,
                BillingTypes.GetBillingQuoteCommand(
                    quote_id=quote.id, request=quote.request
                ),
                clock=lambda: NOW,
            )
            assert stored == quote
            reservation = await BillingCreditService.reserve_credit(
                session, _reserve_command(stored), clock=lambda: NOW
            )
            assert reservation.reserved_credit == quote.price.final_price_credit
            await _finalize_reservation(session, reservation, uuid4())
    await _assert_durable_state(
        db,
        funded_request.user_id,
        balance=5,
        reserved=0,
        quotes=2,
        reservations=2,
        debits=2,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["reserve", "commit", "release"])
async def test_outer_error_rolls_back_quote_and_entire_credit_lifecycle(
    db: AsyncSession,
    funded_request: BillingTypes.BillingRequestInfo,
    configuration: BillingPricingService.BillingPricingConfiguration,
    stage: str,
) -> None:
    with pytest.raises(RuntimeError, match="outer caller failed"):
        async with use_case_transaction(db):
            quote = await BillingQuoteService.create_billing_quote(
                db,
                BillingTypes.CreateBillingQuoteCommand(request=funded_request),
                configuration=configuration,
                clock=lambda: NOW,
            )
            reservation = await BillingCreditService.reserve_credit(
                db, _reserve_command(quote), clock=lambda: NOW
            )
            if stage != "reserve":
                await _finalize_reservation(
                    db, reservation, uuid4() if stage == "commit" else None
                )
            raise RuntimeError("outer caller failed after billing service returned")
    await _assert_durable_state(
        db,
        funded_request.user_id,
        balance=20,
        reserved=0,
        quotes=0,
        reservations=0,
        debits=0,
    )
    # Rollback leaves no orphaned quote/key/ledger, so the same request can retry.
    async with use_case_transaction(db):
        retried = await BillingQuoteService.create_billing_quote(
            db,
            BillingTypes.CreateBillingQuoteCommand(request=funded_request),
            configuration=configuration,
            clock=lambda: NOW,
        )
        assert retried.id != quote.id
        reserved = await BillingCreditService.reserve_credit(
            db, _reserve_command(retried), clock=lambda: NOW
        )
        await _finalize_reservation(db, reserved, uuid4())
    await _assert_durable_state(
        db,
        funded_request.user_id,
        balance=10,
        reserved=0,
        quotes=1,
        reservations=1,
        debits=1,
    )
