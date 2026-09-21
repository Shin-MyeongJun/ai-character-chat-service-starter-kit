"""Quote service tests; in-memory doubles do not claim PostgreSQL atomicity."""

import asyncio
import copy
from contextlib import asynccontextmanager
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.db.models.billing_quote import BillingQuote
from app.db.models.identity import User
from app.db.transaction import use_case_transaction
from app.modules.commerce.billing import repository as Repository
from app.modules.commerce.billing import types as Types
from app.modules.commerce.billing.mapper import quotes as QuotePersistenceMapper
from app.modules.commerce.billing.service import quotes as QuoteService
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from test_billing_prices import (  # noqa: F401
    AdjustmentAdapter,
    _configuration,
    _request_info,
    registry,
)

NOW = datetime(2026, 9, 21, tzinfo=UTC)


@pytest.fixture
def quote_store(monkeypatch):
    rows = {}

    @asynccontextmanager
    async def transaction(session):
        yield

    async def get_by_key(session, user_id, request_key):
        return next(
            (
                row
                for row in rows.values()
                if row.user_id == user_id and row.request_key == request_key
            ),
            None,
        )

    async def get_by_id(session, user_id, quote_id):
        row = rows.get(quote_id)
        return row if row is not None and row.user_id == user_id else None

    async def create_quote(session, *, quote_id, **fields):
        row = BillingQuote(id=quote_id, **copy.deepcopy(fields))
        rows[row.id] = row
        return row

    monkeypatch.setattr(QuoteService, "use_case_transaction", transaction)
    monkeypatch.setattr(QuoteService, "lock_key", AsyncMock())
    monkeypatch.setattr(Repository, "get_billing_quote_by_key", get_by_key)
    monkeypatch.setattr(Repository, "get_billing_quote", get_by_id)
    monkeypatch.setattr(Repository, "create_billing_quote", create_quote)
    return rows


@pytest.mark.asyncio
async def test_persisted_roundtrip_and_policy_changes(
    quote_store, request_info, configuration
):
    command = Types.CreateBillingQuoteCommand(request=request_info)
    original = await QuoteService.create_billing_quote(
        None, command, configuration=configuration, clock=lambda: NOW
    )
    frozen_snapshot = copy.deepcopy(quote_store[original.id].price_snapshot)
    # Replace book, costs, TTL, policy order/config. Retry must use the first snapshot.
    changed = replace(
        configuration,
        price_book=replace(
            configuration.price_book, version="test-v2", safety_factor=Decimal("10")
        ),
        quote_ttl_seconds=3600,
        policies=registry(AdjustmentAdapter("new", multiplier=Decimal("0"))),
    )
    retry = await QuoteService.create_billing_quote(
        None, command, configuration=changed, clock=lambda: NOW + timedelta(seconds=20)
    )
    no_book_retry = await QuoteService.create_billing_quote(
        None,
        command,
        configuration=replace(changed, price_book=None),
        clock=lambda: NOW,
    )
    assert original == retry == no_book_retry
    assert len(quote_store) == 1
    assert quote_store[original.id].price_snapshot == frozen_snapshot
    assert original.price.basis.input_cost_per_token == Decimal(".01")
    assert original.price.policy_results[0].reason
    query = Types.GetBillingQuoteCommand(quote_id=original.id, request=request_info)
    assert (
        await QuoteService.get_billing_quote(None, query, clock=lambda: NOW) == original
    )
    assert (
        await QuoteService.validate_billing_quote(None, query, clock=lambda: NOW)
        == original
    )
    with pytest.raises(FrozenInstanceError):
        original.price.final_price_credit = 0
    with pytest.raises(FrozenInstanceError):
        original.price.basis.safety_factor = Decimal(0)


@pytest.mark.asyncio
async def test_exact_expiration_boundary_and_retry_preserves_expiry(
    quote_store, request_info, configuration
):
    command = Types.CreateBillingQuoteCommand(request=request_info)
    info = await QuoteService.create_billing_quote(
        None, command, configuration=configuration, clock=lambda: NOW
    )
    query = Types.GetBillingQuoteCommand(quote_id=info.id, request=request_info)
    before = await QuoteService.validate_billing_quote(
        None, query, clock=lambda: info.expires_at - timedelta(microseconds=1)
    )
    assert before.status is Types.BillingQuoteStatus.QUOTED
    expired = await QuoteService.get_billing_quote(
        None, query, clock=lambda: info.expires_at
    )
    assert expired.status is Types.BillingQuoteStatus.EXPIRED
    assert expired.price == info.price
    with pytest.raises(Types.BillingQuoteExpiredError):
        await QuoteService.validate_billing_quote(
            None, query, clock=lambda: info.expires_at
        )
    retried = await QuoteService.create_billing_quote(
        None, command, configuration=configuration, clock=lambda: info.expires_at
    )
    assert retried == expired
    assert quote_store[info.id].expires_at == info.expires_at


@pytest.mark.asyncio
async def test_user_request_and_all_execution_conditions_bound(
    quote_store, request_info, configuration
):
    info = await QuoteService.create_billing_quote(
        None,
        Types.CreateBillingQuoteCommand(request=request_info),
        configuration=configuration,
        clock=lambda: NOW,
    )
    mismatches = (
        replace(request_info, operation_fingerprint="sha256:" + "b" * 64),
        replace(
            request_info, operation_kind=Types.BillingOperationKind.USER_CONTINUATION
        ),
        replace(request_info, product=None),
        replace(
            request_info,
            product=replace(request_info.product, product_snapshot_id=uuid4()),
        ),
        replace(
            request_info, product=replace(request_info.product, product_id=uuid4())
        ),
        replace(request_info, input_tokens=61),
        replace(request_info, max_output_tokens=31),
        *(
            replace(request_info, execution=replace(request_info.execution, **fields))
            for fields in (
                {"model_id": uuid4()},
                {"provider": "changed"},
                {"model": "changed"},
                {"reasoning_effort": "high"},
                {"pricing_settings": (Types.PricingSettingInfo(name="x", value="1"),)},
            )
        ),
    )
    for different in mismatches:
        with pytest.raises(Types.BillingQuoteConflictError):
            await QuoteService.get_billing_quote(
                None,
                Types.GetBillingQuoteCommand(quote_id=info.id, request=different),
                clock=lambda: NOW,
            )
        with pytest.raises(Types.BillingQuoteConflictError):
            await QuoteService.create_billing_quote(
                None,
                Types.CreateBillingQuoteCommand(request=different),
                configuration=configuration,
                clock=lambda: NOW,
            )
    with pytest.raises(Types.BillingQuoteConflictError):
        await QuoteService.get_billing_quote(
            None,
            Types.GetBillingQuoteCommand(
                quote_id=info.id, request=replace(request_info, request_key=uuid4())
            ),
            clock=lambda: NOW,
        )
    with pytest.raises(Types.BillingQuoteNotFoundError):
        await QuoteService.get_billing_quote(
            None,
            Types.GetBillingQuoteCommand(
                quote_id=info.id, request=replace(request_info, user_id=uuid4())
            ),
            clock=lambda: NOW,
        )
    with pytest.raises(Types.BillingQuoteNotFoundError):
        await QuoteService.get_billing_quote(
            None,
            Types.GetBillingQuoteCommand(quote_id=uuid4(), request=request_info),
            clock=lambda: NOW,
        )


@pytest.mark.asyncio
async def test_invalid_input_cannot_save_quote(
    quote_store, request_info, configuration
):
    command = Types.CreateBillingQuoteCommand(request=request_info)
    with pytest.raises(Types.BillingPricingError, match="timezone"):
        await QuoteService.create_billing_quote(
            None,
            command,
            configuration=configuration,
            clock=lambda: NOW.replace(tzinfo=None),
        )
    with pytest.raises(Types.BillingPricingError, match="not configured"):
        await QuoteService.create_billing_quote(
            None,
            command,
            configuration=replace(configuration, price_book=None),
            clock=lambda: NOW,
        )
    assert not quote_store


def test_mapper_rejects_unknown_snapshot_version():
    row = SimpleNamespace(
        request_snapshot={"schema_version": 2}, price_snapshot={"schema_version": 1}
    )
    with pytest.raises(ValueError, match="schema"):
        QuotePersistenceMapper.quote_entity_to_info(row)


@pytest.mark.asyncio
async def test_postgres_quote_roundtrip_and_concurrent_retries(
    db, request_info, configuration
):
    async with db.begin():
        db.add(
            User(id=request_info.user_id, email=f"{request_info.user_id}@quote.test")
        )

    async def create_quote():
        async with AsyncSession(db.bind, expire_on_commit=False) as session:
            return await QuoteService.create_billing_quote(
                session,
                Types.CreateBillingQuoteCommand(request=request_info),
                configuration=configuration,
                clock=lambda: NOW,
            )

    left, right = await asyncio.gather(create_quote(), create_quote())
    assert left == right
    async with db.begin():
        assert await db.scalar(select(func.count()).select_from(BillingQuote)) == 1
        loaded = await QuoteService.validate_billing_quote(
            db,
            Types.GetBillingQuoteCommand(quote_id=left.id, request=request_info),
            clock=lambda: NOW,
        )
        assert loaded == left
    changed = replace(configuration, price_book=None, policies=registry())
    assert (
        await QuoteService.create_billing_quote(
            db,
            Types.CreateBillingQuoteCommand(request=request_info),
            configuration=changed,
            clock=lambda: NOW,
        )
        == left
    )


@pytest.mark.asyncio
async def test_postgres_quote_participates_in_outer_rollback(
    db, request_info, configuration
):
    async with db.begin():
        db.add(
            User(id=request_info.user_id, email=f"{request_info.user_id}@quote.test")
        )
    with pytest.raises(RuntimeError, match="rollback test"):
        async with use_case_transaction(db):
            await QuoteService.create_billing_quote(
                db,
                Types.CreateBillingQuoteCommand(request=request_info),
                configuration=configuration,
                clock=lambda: NOW,
            )
            raise RuntimeError("rollback test")
    async with db.begin():
        assert await db.scalar(select(func.count()).select_from(BillingQuote)) == 0


@pytest.mark.asyncio
async def test_postgres_conflict_does_not_replace_original(
    db, request_info, configuration
):
    async with db.begin():
        db.add(
            User(id=request_info.user_id, email=f"{request_info.user_id}@quote.test")
        )
    original = await QuoteService.create_billing_quote(
        db,
        Types.CreateBillingQuoteCommand(request=request_info),
        configuration=configuration,
        clock=lambda: NOW,
    )
    with pytest.raises(Types.BillingQuoteConflictError):
        await QuoteService.create_billing_quote(
            db,
            Types.CreateBillingQuoteCommand(
                request=replace(request_info, input_tokens=61)
            ),
            configuration=configuration,
            clock=lambda: NOW,
        )
    async with db.begin():
        loaded = await QuoteService.get_billing_quote(
            db,
            Types.GetBillingQuoteCommand(quote_id=original.id, request=request_info),
            clock=lambda: NOW,
        )
    assert loaded == original
