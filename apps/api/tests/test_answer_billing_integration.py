"""Actual PostgreSQL + public answer/billing/credit services, deterministic LLM."""

import asyncio
import hashlib
import json
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid5

import pytest
from answer_billing_support import answer_pricing
from app.db.models.billing import UsageLog
from app.db.models.billing_quote import BillingQuote
from app.db.models.chat import Conversation, Message
from app.db.models.credit import (
    CreditAccount,
    CreditBalance,
    CreditReservation,
    CreditTransaction,
    CreditTransactionEntry,
    CreditWallet,
)
from app.db.models.memory import MemoryJob
from app.db.models.model_routing import Model
from app.db.models.product_usage import ProductGeneration
from app.db.transaction import use_case_transaction
from app.modules.chatting.chat import service as ChatService
from app.modules.chatting.chat import types as ChatTypes
from app.modules.chatting.chat.service.workflow import answers as Answers
from app.modules.chatting.conversation import service as ConversationService
from app.modules.chatting.conversation import types as ConversationTypes
from app.modules.chatting.conversation.service.command import start_conversation
from app.modules.chatting.conversation.service.command.versions import switch_version
from app.modules.commerce.billing import types as BillingTypes
from app.modules.commerce.credit import types as CreditTypes
from app.modules.commerce.credit.service import query as CreditQueryService
from app.modules.content.product import types as ProductTypes
from app.modules.content.product.service.command.releases import publish_product
from app.modules.llm import types as LLMTypes
from credit_support import fund_credit
from sqlalchemy import func, select, update
from test_nonstream_answers import result, setup_answer

pytestmark = pytest.mark.asyncio


async def check_state(orchestrator, command, *, status, balance, reserved, charge):
    async with orchestrator.sessions() as session:
        run = (
            await session.scalars(
                select(ProductGeneration).where(
                    ProductGeneration.request_key == command.request_key
                )
            )
        ).one()
        assert run.status == status
        binding = run.answer_metadata["billing"]
        reservation = await CreditQueryService.get_credit_reservation(
            session,
            CreditTypes.GetCreditReservationCommand(
                user_id=command.user_id,
                currency_code="CREDIT",
                namespace="billing",
                request_key=UUID(binding["request_key"]),
            ),
        )
        expected = (
            "reserved"
            if status == "pending"
            else ("committed" if status == "succeeded" else "released")
        )
        assert reservation.status == expected
        wallet = await CreditQueryService.get_credit_balance(
            session,
            CreditTypes.GetCreditBalanceCommand(
                user_id=command.user_id, currency_code="CREDIT"
            ),
        )
        assert wallet.balance_credit == balance
        assert wallet.reserved_credit == reserved
        usage = await session.scalar(
            select(UsageLog).where(UsageLog.generation_id == run.id)
        )
        assert (usage.cost_credit if usage else 0) == charge
        debits = (
            await session.scalars(
                select(CreditTransaction).where(
                    CreditTransaction.operation == "consume",
                    CreditTransaction.reference_id == run.id,
                )
            )
        ).all()
        assert len(debits) == (1 if status == "succeeded" else 0)
        if debits:
            assert -debits[0].amount == reservation.reserved_credit == charge
            entries = await session.scalar(
                select(func.sum(CreditTransactionEntry.amount)).where(
                    CreditTransactionEntry.transaction_id == debits[0].id
                )
            )
            assert entries == debits[0].amount
        count = await session.scalar(
            select(func.count())
            .select_from(Message)
            .where(Message.generation_id == run.id, Message.generated_by_ai.is_(True))
        )
        assert count == (1 if status == "succeeded" else 0)
        return run, reservation


async def assert_no_attempt(orchestrator):
    async with orchestrator.sessions() as session:
        for model in (
            ProductGeneration,
            BillingQuote,
            CreditReservation,
            UsageLog,
            MemoryJob,
        ):
            assert await session.scalar(select(func.count()).select_from(model)) == 0


async def test_success_pins_prompt_quote_output_and_free_paid_allocation(db):
    orchestrator, command, text = await setup_answer(db, balance=3)
    async with db.begin():
        await fund_credit(db, command.user_id, 20, bucket=CreditTypes.CreditBucket.PAID)

    async def generate(value):
        # No conversation, wallet or generation lock survives into external I/O.
        async with orchestrator.sessions() as session, session.begin():
            for model in (Conversation, ProductGeneration, CreditWallet):
                await session.execute(select(model).with_for_update(nowait=True))
            run = (await session.scalars(select(ProductGeneration))).one()
            quote = (await session.scalars(select(BillingQuote))).one()
            meta = run.answer_metadata
            assert (
                quote.request_snapshot["value"]["input_tokens"]
                == meta["estimated_prompt_tokens"]
            )
            assert (
                quote.request_snapshot["value"]["max_output_tokens"]
                == value.max_output_tokens
                == 1200
            )
            assert (
                hashlib.sha256(value.request_json.encode()).hexdigest()
                == meta["prompt_digest"]
            )
            messages = json.loads(value.request_json)["messages"]
            assert (
                sum(len(m["content"].encode()) + 32 for m in messages) + 32
                == meta["estimated_prompt_tokens"]
            )
            assert meta["token_estimator"] == Answers.TOKEN_ESTIMATOR
            assert UUID(meta["billing"]["request_key"]) == uuid5(
                Answers.ANSWER_KEY_NAMESPACE, f"{command.user_id}:{command.request_key}"
            )
            await fund_credit(session, command.user_id, 4)
        return result()

    text.generate_text.side_effect = generate
    answer = await orchestrator.generate_answer(command)
    assert answer.status == "succeeded"
    _, reservation = await check_state(
        orchestrator, command, status="succeeded", balance=17, reserved=0, charge=10
    )
    assert (reservation.free_amount, reservation.paid_amount) == (3, 7)
    assert await orchestrator.generate_answer(command) == answer
    assert text.generate_text.await_count == 1


async def test_insufficient_has_no_partial_generation_quote_or_llm(db):
    orchestrator, command, text = await setup_answer(db, balance=9)
    with pytest.raises(BillingTypes.InsufficientCreditError):
        await orchestrator.generate_answer(command)
    text.generate_text.assert_not_awaited()
    await assert_no_attempt(orchestrator)


@pytest.mark.parametrize(
    "kind", [LLMTypes.LLMErrorKind.AUTHENTICATION, LLMTypes.LLMErrorKind.TIMEOUT]
)
async def test_provider_failure_and_timeout_release_only_after_durable_failure(
    db, kind
):
    orchestrator, command, text = await setup_answer(db)
    text.generate_text.side_effect = LLMTypes.LLMError(
        "synthetic",
        kind=kind,
        provider="openai",
        model="gpt-test",
        retryable=True,
    )
    answer = await orchestrator.generate_answer(command)
    assert answer.status == "failed"
    await check_state(
        orchestrator, command, status="failed", balance=20, reserved=0, charge=0
    )
    assert await orchestrator.generate_answer(command) == answer
    assert text.generate_text.await_count == 1


async def test_simultaneous_same_key_before_reservation_calls_once(db):
    orchestrator, command, text = await setup_answer(db)
    barrier = asyncio.Barrier(5)

    async def retrieve(_):
        await asyncio.wait_for(barrier.wait(), 10)
        return []

    orchestrator.retriever.retrieve_memories.side_effect = retrieve
    answers = await asyncio.wait_for(
        asyncio.gather(*(orchestrator.generate_answer(command) for _ in range(5))), 20
    )
    assert len({a.generation_id for a in answers}) == 1
    assert text.generate_text.await_count == 1
    await check_state(
        orchestrator, command, status="succeeded", balance=10, reserved=0, charge=10
    )
    async with db.begin():
        for model in (ProductGeneration, BillingQuote, CreditReservation):
            assert await db.scalar(select(func.count()).select_from(model)) == 1


async def test_different_conversations_compete_for_one_wallet(db):
    orchestrator, command, text = await setup_answer(db, balance=10)
    async with db.begin():
        conversation = await ConversationService.get_owned_conversation(
            db,
            ConversationTypes.OwnedConversationCommand(
                conversation_id=command.conversation_id, user_id=command.user_id
            ),
        )
    other = await start_conversation(
        db,
        ConversationTypes.StartConversationCommand(
            product_id=conversation.product_id, user_id=command.user_id
        ),
    )
    message = await ChatService.create_message(
        db,
        ChatTypes.CreateMessageCommand(
            conversation_id=other.id,
            user_id=command.user_id,
            request_key="input",
            content="second",
        ),
    )
    second = replace(
        command,
        conversation_id=other.id,
        input_message_id=message.id,
        request_key="answer-2",
    )
    barrier = asyncio.Barrier(2)

    async def retrieve(_):
        await asyncio.wait_for(barrier.wait(), 10)
        return []

    orchestrator.retriever.retrieve_memories.side_effect = retrieve
    answers = await asyncio.wait_for(
        asyncio.gather(
            orchestrator.generate_answer(command),
            orchestrator.generate_answer(second),
            return_exceptions=True,
        ),
        20,
    )
    assert (
        sum(isinstance(a, BillingTypes.InsufficientCreditError) for a in answers) == 1
    )
    assert text.generate_text.await_count == 1
    winner = second if isinstance(answers[0], Exception) else command
    await check_state(
        orchestrator, winner, status="succeeded", balance=0, reserved=0, charge=10
    )


@pytest.mark.parametrize("change", ["message", "model", "history", "config"])
async def test_preparation_changes_rejected_before_reservation(db, change):
    orchestrator, command, text = await setup_answer(db)

    async def retrieve(_):
        async with orchestrator.sessions() as session:
            if change == "message":
                await ChatService.replace_message(
                    session,
                    ChatTypes.ReplaceMessageCommand(
                        conversation_id=command.conversation_id,
                        user_id=command.user_id,
                        message_id=command.input_message_id,
                        expected_revision=1,
                        content="changed",
                    ),
                )
            elif change == "history":
                await ConversationService.advance_history_revision(
                    session,
                    ConversationTypes.AdvanceHistoryRevisionCommand(
                        conversation_id=command.conversation_id, user_id=command.user_id
                    ),
                )
            elif change == "model":
                async with session.begin():
                    await session.execute(
                        update(Model).values(model_name="changed-model")
                    )
            else:
                orchestrator.config = replace(orchestrator.config, response_tokens=1100)
        return []

    orchestrator.retriever.retrieve_memories.side_effect = retrieve
    with pytest.raises(ChatTypes.MessageConflictError):
        await orchestrator.generate_answer(command)
    text.generate_text.assert_not_awaited()
    # Message edit legitimately invalidates memory; no billable attempt survives.
    await assert_no_attempt(orchestrator)


@pytest.mark.parametrize("success", [True, False])
async def test_settlement_failure_rolls_back_everything_then_replays_staging(
    db, monkeypatch, success
):
    orchestrator, command, text = await setup_answer(db)
    method = "commit_credit_reservation" if success else "release_credit_reservation"
    original = getattr(Answers.BillingCreditService, method)
    if not success:
        text.generate_text.side_effect = ValueError("empty_response")

    async def fail_after_write(*args):
        await original(*args)
        raise RuntimeError("injected after settlement and ledger writes")

    monkeypatch.setattr(Answers.BillingCreditService, method, fail_after_write)
    with pytest.raises(ChatTypes.AnswerStorageError):
        await orchestrator.generate_answer(command)
    run, _ = await check_state(
        orchestrator, command, status="pending", balance=20, reserved=10, charge=0
    )
    assert run.answer_metadata["phase"] == "result_ready"
    async with db.begin():
        assert await db.scalar(select(func.count()).select_from(MemoryJob)) == 0
    monkeypatch.setattr(Answers.BillingCreditService, method, original)
    # A new orchestrator proves that only persisted staging is needed, even with
    # pricing removed and before the original lease expires.
    restarted = Answers.AnswerOrchestrator(
        orchestrator.sessions, text, orchestrator.retriever
    )
    answer = await restarted.generate_answer(command)
    status = "succeeded" if success else "failed"
    assert answer.status == status
    await check_state(
        orchestrator,
        command,
        status=status,
        balance=10 if success else 20,
        reserved=0,
        charge=10 if success else 0,
    )
    assert text.generate_text.await_count == 1


async def test_expired_execution_is_fenced_and_late_result_cannot_charge(db):
    orchestrator, command, text = await setup_answer(db)
    entered, release = asyncio.Event(), asyncio.Event()

    async def generate(_):
        entered.set()
        await release.wait()
        return result()

    text.generate_text.side_effect = generate
    task = asyncio.create_task(orchestrator.generate_answer(command))
    await asyncio.wait_for(entered.wait(), 5)
    try:
        async with db.begin():
            await db.execute(
                update(ProductGeneration).values(
                    answer_lease_until=datetime.now(UTC) - timedelta(seconds=1)
                )
            )
        assert await orchestrator.recover_answers() == 1
        await check_state(
            orchestrator, command, status="failed", balance=20, reserved=0, charge=0
        )
    finally:
        release.set()
        await task
    late = await task
    assert late.status == "failed" and late.uncertain
    assert (await orchestrator.generate_answer(command)) == late
    await check_state(
        orchestrator, command, status="failed", balance=20, reserved=0, charge=0
    )
    assert text.generate_text.await_count == 1


async def test_quote_expiry_does_not_release_live_execution_and_replay_preserves_price(
    db,
):
    orchestrator, command, text = await setup_answer(db)
    entered, release = asyncio.Event(), asyncio.Event()

    async def generate(_):
        entered.set()
        await release.wait()
        return result()

    text.generate_text.side_effect = generate
    task = asyncio.create_task(orchestrator.generate_answer(command))
    await asyncio.wait_for(entered.wait(), 5)
    try:
        async with db.begin():
            await db.execute(
                update(BillingQuote).values(
                    created_at=datetime.now(UTC) - timedelta(seconds=61),
                    expires_at=datetime.now(UTC) - timedelta(seconds=1),
                )
            )
        orchestrator.pricing = answer_pricing(
            orchestrator.pricing.price_book.models[0].execution.model_id, price=99
        )
        assert await orchestrator.recover_answers() == 0
        assert (await orchestrator.generate_answer(command)).status == "pending"
        await check_state(
            orchestrator, command, status="pending", balance=20, reserved=10, charge=0
        )
    finally:
        release.set()
        await task
    answer = await task
    assert await orchestrator.generate_answer(command) == answer
    await check_state(
        orchestrator, command, status="succeeded", balance=10, reserved=0, charge=10
    )
    assert text.generate_text.await_count == 1


async def test_stale_success_releases_without_usage_charge(db):
    orchestrator, command, text = await setup_answer(db)

    async def generate(_):
        async with orchestrator.sessions() as session:
            conversation = await ConversationService.get_owned_conversation(
                session,
                ConversationTypes.OwnedConversationCommand(
                    conversation_id=command.conversation_id, user_id=command.user_id
                ),
            )
        async with orchestrator.sessions() as session:
            release = await publish_product(
                session,
                ProductTypes.PublishCommand(
                    product_id=conversation.product_id,
                    owner_id=command.user_id,
                    value=ProductTypes.ReleaseNoteCommand("Next", "Next", True),
                ),
            )
            await switch_version(
                session,
                ConversationTypes.SwitchVersionCommand(
                    conversation_id=command.conversation_id,
                    user_id=command.user_id,
                    target_snapshot_id=release.snapshot_id,
                ),
            )
        return result()

    text.generate_text.side_effect = generate
    assert (await orchestrator.generate_answer(command)).status == "stale"
    await check_state(
        orchestrator, command, status="stale", balance=20, reserved=0, charge=0
    )
    async with db.begin():
        assert await db.scalar(select(func.count()).select_from(MemoryJob)) == 0


@pytest.mark.parametrize("phase", ["reserved", "calling", "result_ready", "succeeded"])
async def test_lost_commit_acknowledgement_never_repeats_llm_or_releases_blindly(
    db, monkeypatch, phase
):
    orchestrator, command, text = await setup_answer(db)
    injected = False

    @asynccontextmanager
    async def lose_ack(session):
        nonlocal injected
        owned = session.info.get("application_use_case_transaction") is None
        lost = False
        async with use_case_transaction(session):
            yield
            if owned and not injected:
                run = await session.scalar(select(ProductGeneration))
                lost = run is not None and (
                    run.status == "succeeded"
                    if phase == "succeeded"
                    else run.status == "pending"
                    and run.answer_metadata is not None
                    and run.answer_metadata.get("phase") == phase
                )
        if lost:
            injected = True
            raise RuntimeError("commit acknowledged late")

    # All three public writes use the common transaction context. Replace the
    # imported boundary only, commit to PostgreSQL first, then lose its response.
    from app.modules.chatting.chat.service.command import answers as ChatAnswers

    monkeypatch.setattr(Answers, "use_case_transaction", lose_ack)
    monkeypatch.setattr(ChatAnswers, "use_case_transaction", lose_ack)
    if phase == "calling":
        with pytest.raises(ChatTypes.AnswerStorageError):
            await orchestrator.generate_answer(command)
    else:
        answer = await orchestrator.generate_answer(command)
        assert answer.status == ("pending" if phase == "reserved" else "succeeded")
    assert injected
    if phase in {"reserved", "calling"}:
        text.generate_text.assert_not_awaited()
        await check_state(
            orchestrator, command, status="pending", balance=20, reserved=10, charge=0
        )
        async with db.begin():
            await db.execute(
                update(ProductGeneration).values(
                    answer_lease_until=datetime.now(UTC) - timedelta(seconds=1)
                )
            )
        await orchestrator.generate_answer(command)
        await check_state(
            orchestrator, command, status="failed", balance=20, reserved=0, charge=0
        )
    else:
        assert text.generate_text.await_count == 1
        assert (await orchestrator.generate_answer(command)).status == "succeeded"
        await check_state(
            orchestrator, command, status="succeeded", balance=10, reserved=0, charge=10
        )


async def test_legacy_credit_classification_is_not_bypassed(db):
    orchestrator, command, text = await setup_answer(db)
    async with db.begin():
        db.add(CreditAccount(user_id=command.user_id, balance=100))
    with pytest.raises(BillingTypes.CreditAccountNotFoundError):
        await orchestrator.generate_answer(command)
    await assert_no_attempt(orchestrator)
    text.generate_text.assert_not_awaited()
    async with db.begin():
        assert (await db.get(CreditAccount, command.user_id)).balance == 100
        assert await db.scalar(select(func.sum(CreditBalance.balance))) == 20


async def test_missing_pricing_is_not_free_generation(db):
    orchestrator, command, text = await setup_answer(db)
    orchestrator.pricing = None
    with pytest.raises(BillingTypes.BillingPricingError):
        await orchestrator.generate_answer(command)
    await assert_no_attempt(orchestrator)
    text.generate_text.assert_not_awaited()


async def test_cancel_is_atomic_release_and_cannot_be_reexecuted(db):
    orchestrator, command, text = await setup_answer(db)
    entered = asyncio.Event()

    async def generate(_):
        entered.set()
        await asyncio.Future()

    text.generate_text.side_effect = generate
    task = asyncio.create_task(orchestrator.generate_answer(command))
    await asyncio.wait_for(entered.wait(), 5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await check_state(
        orchestrator, command, status="cancelled", balance=20, reserved=0, charge=0
    )
    assert (await orchestrator.generate_answer(command)).status == "cancelled"
    assert text.generate_text.await_count == 1


async def test_legacy_staged_answer_recovers_without_retroactive_charge(db):
    orchestrator, command, text = await setup_answer(db)
    # Manufacture a pre-integration staged result using the original public API.
    async with db.begin():
        current = await ChatService.get_answer_input(
            db,
            ChatTypes.GetAnswerInputCommand(
                conversation_id=command.conversation_id,
                user_id=command.user_id,
                message_id=command.input_message_id,
                expected_revision=1,
            ),
        )
    run = await ChatService.begin_generation(
        db,
        ChatTypes.BeginGenerationCommand(
            conversation_id=command.conversation_id,
            user_id=command.user_id,
            request_key=command.request_key,
            input_message_id=current.id,
            expected_revision=1,
            input_text=current.content,
        ),
    )
    await ChatService.update_answer(
        db,
        ChatTypes.UpdateAnswerCommand(
            generation_id=run.id,
            user_id=command.user_id,
            metadata={
                "phase": "result_ready",
                "outcome": "succeeded",
                "content": "legacy result",
                "usage": {"input_tokens": 100, "output_tokens": 30},
                "identity": {
                    "input_message_id": str(current.id),
                    "expected_revision": 1,
                    "product_character_id": str(command.product_character_id),
                },
            },
            lease_until=datetime.now(UTC) - timedelta(seconds=1),
        ),
    )
    orchestrator.pricing = None
    answer = await orchestrator.generate_answer(command)
    assert answer.status == "succeeded" and answer.content == "legacy result"
    assert await orchestrator.generate_answer(command) == answer
    text.generate_text.assert_not_awaited()
    async with db.begin():
        assert await db.scalar(select(func.count()).select_from(CreditReservation)) == 0
        assert await db.scalar(select(func.count()).select_from(BillingQuote)) == 0
        assert (await db.scalar(select(UsageLog))).cost_credit == 0
        assert await db.scalar(select(func.sum(CreditBalance.balance))) == 20


async def test_failed_recovery_release_rolls_back_and_fences_late_worker(
    db, monkeypatch
):
    orchestrator, command, text = await setup_answer(db)
    entered, release = asyncio.Event(), asyncio.Event()

    async def generate(_):
        entered.set()
        await release.wait()
        return result()

    text.generate_text.side_effect = generate
    task = asyncio.create_task(orchestrator.generate_answer(command))
    await asyncio.wait_for(entered.wait(), 5)
    original = Answers.BillingCreditService.release_credit_reservation

    async def fail_after_release(*args):
        await original(*args)
        raise RuntimeError("release failed before commit")

    try:
        async with db.begin():
            await db.execute(
                update(ProductGeneration).values(
                    answer_lease_until=datetime.now(UTC) - timedelta(seconds=1)
                )
            )
        monkeypatch.setattr(
            Answers.BillingCreditService,
            "release_credit_reservation",
            fail_after_release,
        )
        assert await orchestrator.recover_answers() == 1
        run, _ = await check_state(
            orchestrator, command, status="pending", balance=20, reserved=10, charge=0
        )
        assert run.answer_metadata["phase"] == "calling"
        monkeypatch.setattr(
            Answers.BillingCreditService, "release_credit_reservation", original
        )
        assert (await orchestrator.generate_answer(command)).status == "failed"
    finally:
        release.set()
        await task
    await check_state(
        orchestrator, command, status="failed", balance=20, reserved=0, charge=0
    )
    assert text.generate_text.await_count == 1


async def test_committed_charge_cannot_be_refunded_by_release(db):
    orchestrator, command, _ = await setup_answer(db)
    await orchestrator.generate_answer(command)
    run, _ = await check_state(
        orchestrator, command, status="succeeded", balance=10, reserved=0, charge=10
    )
    billing = run.answer_metadata["billing"]
    with pytest.raises(BillingTypes.CreditReservationConflictError):
        async with orchestrator.sessions() as session, use_case_transaction(session):
            await Answers.BillingCreditService.release_credit_reservation(
                session,
                BillingTypes.ReleaseCreditReservationCommand(
                    user_id=command.user_id,
                    request_key=UUID(billing["request_key"]),
                    reservation_id=UUID(billing["reservation_id"]),
                ),
            )
    await check_state(
        orchestrator, command, status="succeeded", balance=10, reserved=0, charge=10
    )
