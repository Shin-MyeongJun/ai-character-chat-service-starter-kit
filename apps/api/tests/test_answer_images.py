"""U19 a7: candidate scope, durable placements, atomic unlock and occurrence reads."""

import asyncio
import json
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import Connection, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from test_answer_billing_integration import check_state
from test_character_media import media as media_fixture
from test_nonstream_answers import result, setup_answer
from test_product_file_versions import image_upload, workflow

from app.db.models.chat import Conversation, Message
from app.db.models.memory import MemoryJob
from app.db.models.product_album import ProductImageUnlock
from app.db.models.product_usage import ProductGeneration
from app.db.models.snapshot.product import ProductSnapshot
from app.http import dependencies
from app.http.media import router as media_router
from app.modules.chatting.chat import service as ChatService
from app.modules.chatting.chat import types as ChatTypes
from app.modules.chatting.chat.mapper.schema.messages import message_info_to_response
from app.modules.chatting.chat.service import answer_images as Images
from app.modules.chatting.chat.service.query import messages as Messages
from app.modules.chatting.chat.service.query.image_blocks import (
    authorize_message_image_block,
)
from app.modules.chatting.chat.service.workflow import answers as Answers
from app.modules.chatting.prompt import types as PromptTypes
from app.modules.commerce.billing import types as BillingTypes
from app.modules.content.character.service.workflow.media import CharacterMediaWorkflow
from app.modules.content.product import types as ProductTypes
from app.modules.content.product.service.command.file_versions import (
    retain_product_file_version,
)
from app.modules.content.product.service.workflow.file_versions import (
    ProductFileVersionWorkflow,
)
from app.modules.llm import types as LLMTypes

media = media_fixture


def item(
    character_id: UUID,
    *,
    item_id: UUID | None = None,
    file_id: UUID | None = None,
    target: ProductTypes.ProductJsonObject | None = None,
) -> ProductTypes.ProductJsonObject:
    return {
        "image_item_id": str(item_id or uuid4()),
        "file_version_id": str(file_id or uuid4()),
        "target": target
        or {"kind": "character", "product_character_id": str(character_id)},
        "kind": "situation",
        "tags": ["smile"],
        "alt": "smiling character",
    }


def candidates(
    items: Sequence[ProductTypes.ProductJsonObject],
    character_id: UUID,
    books: Sequence[SimpleNamespace] = (),
) -> tuple[ChatTypes.AnswerImageCandidateInfo, ...]:
    runtime = SimpleNamespace(chat_image_items=items, lorebooks=books)
    return Images.select_answer_image_candidates(runtime, character_id, "request-only")


def test_candidate_scope_order_limit_and_request_local_keys() -> None:
    character, book, active, inactive = (uuid4() for _ in range(4))
    own, other = item(character), item(uuid4())

    def lore(entry: UUID, snapshot: UUID = book) -> ProductTypes.ProductJsonObject:
        return item(
            character,
            target={
                "kind": "lore_entry",
                "lorebook_snapshot_id": str(snapshot),
                "lore_entry_id": str(entry),
            },
        )

    active_item = lore(active)
    books = [
        SimpleNamespace(
            snapshot_id=str(book), entries=[{"id": str(active)}], targets=[]
        )
    ]
    selected = candidates(
        [other, own, lore(inactive), lore(active, uuid4()), active_item],
        character,
        books,
    )
    assert [str(c.image.image_item_id) for c in selected] == [
        own["image_item_id"],
        active_item["image_item_id"],
    ]
    assert selected[0].key == "request-only:0"
    assert len(candidates([item(character) for _ in range(30)], character)) == 24
    books[0].targets = [str(uuid4())]
    assert candidates([active_item], character, books) == ()


def test_placements_preserve_text_order_repeats_and_skip_untrusted_values() -> None:
    character = uuid4()
    selected = candidates([item(character), item(character)], character)
    text = "\r\n\r\nFirst.\r\n \r\nSecond.\r\n\r\n"
    proposals = [
        {"candidate_key": selected[1].key, "after_paragraph": 2},
        {"candidate_key": selected[0].key, "after_paragraph": True},
        {"candidate_key": "other-request:0", "after_paragraph": 1},
        {"candidate_key": selected[0].key, "after_paragraph": 3},
        {"candidate_key": selected[0].key, "after_paragraph": -1},
        {"candidate_key": selected[0].key, "after_paragraph": 0},
        {"candidate_key": selected[0].key, "after_paragraph": 1},
        {"candidate_key": selected[1].key, "after_paragraph": 1},
    ]
    content, blocks = Images.resolve_answer_image_blocks(
        json.dumps({"content": text, "image_placements": proposals}), selected
    )
    assert (
        content
        == text
        == "".join(
            b.text for b in blocks if isinstance(b, ProductTypes.TextContentBlockInfo)
        )
    )
    assert [
        b.image_item_id
        for b in blocks
        if isinstance(b, ProductTypes.ImageContentBlockInfo)
    ] == [
        selected[0].image.image_item_id,
        selected[0].image.image_item_id,
        selected[1].image.image_item_id,
    ]
    # A URL or image syntax in ordinary output does not create an occurrence.
    plain = "![untrusted](https://example.invalid/image.png)"
    assert Images.resolve_answer_image_blocks(plain, selected) == (
        plain,
        (ProductTypes.TextContentBlockInfo(plain),),
    )


def test_candidate_budget_removes_from_tail_without_exposing_file_identifiers() -> None:
    character = uuid4()
    selected = candidates([item(character) for _ in range(3)], character)
    base = PromptTypes.PromptInfo(
        json.dumps(
            {"chat_message_format": 1, "messages": [{"role": "user", "content": "Hi"}]}
        ),
        66,
    )
    one, _ = Images.build_image_selection_prompt(base, selected[:1], 100000)
    trimmed, kept = Images.build_image_selection_prompt(
        base, selected, one.estimated_tokens
    )
    assert kept == selected[:1]
    assert trimmed.estimated_tokens <= one.estimated_tokens
    assert str(selected[0].image.file_version_id) not in trimmed.request_json
    assert str(selected[0].image.image_item_id) not in trimmed.request_json
    assert Images.build_image_selection_prompt(base, selected, 66) == (base, ())


async def setup_images(
    db: AsyncSession, media: CharacterMediaWorkflow
) -> tuple[
    Answers.AnswerOrchestrator,
    ChatTypes.GenerateAnswerCommand,
    SimpleNamespace,
    ProductFileVersionWorkflow,
    ProductTypes.ProductJsonObject,
    UUID,
]:
    orchestrator, command, text = await setup_answer(db)
    files = workflow(media)
    async with db.begin():
        conversation = await db.get(Conversation, command.conversation_id)
        product_id, snapshot_id = (
            conversation.product_id,
            conversation.product_snapshot_id,
        )
    uploaded = await files.upload_product_file_version(
        image_upload(product_id, command.user_id, b"original answer image")
    )
    selected = item(command.product_character_id, file_id=uploaded.file_version_id)
    excluded = item(uuid4(), file_id=uploaded.file_version_id)
    async with db.begin():
        snapshot = await db.get(ProductSnapshot, snapshot_id)
        snapshot.snapshot_data = {
            **snapshot.snapshot_data,
            "chat_image_items": [excluded, selected],
        }
    from app.db.transaction import use_case_transaction

    async with use_case_transaction(db):
        await retain_product_file_version(
            db,
            ProductTypes.ProductFileReferenceCommand(
                product_id=product_id,
                file_version_id=uploaded.file_version_id,
                kind="snapshot",
                reference_id=snapshot_id,
            ),
        )

    async def generate(value: LLMTypes.GenerateTextCommand) -> LLMTypes.LLMResultInfo:
        request = json.loads(value.request_json)
        instruction = next(
            m["content"] for m in request["messages"] if "Candidates: " in m["content"]
        )
        offered = json.loads(instruction.split("Candidates: ", 1)[1])
        assert len(offered) == 1
        key = offered[0]["candidate_key"]
        return result(
            json.dumps(
                {
                    "content": "First.\n\nSecond.",
                    "image_placements": [
                        {"candidate_key": key, "after_paragraph": 1},
                        {"candidate_key": key, "after_paragraph": 2},
                        {
                            "candidate_key": excluded["image_item_id"],
                            "after_paragraph": 0,
                        },
                    ],
                }
            )
        )

    text.generate_text.side_effect = generate
    return orchestrator, command, text, files, selected, snapshot_id


@pytest.mark.asyncio
async def test_staged_recovery_atomic_rollback_replay_and_one_charge(
    db: AsyncSession, media: CharacterMediaWorkflow, monkeypatch: pytest.MonkeyPatch
) -> None:
    orchestrator, command, text, _, selected, _ = await setup_images(db, media)
    original = Answers.BillingCreditService.commit_credit_reservation

    # Fail after message creation, unlock, usage and memory enqueue; all roll back.
    async def fail_settlement(
        session: AsyncSession, command: BillingTypes.CommitCreditReservationCommand
    ) -> None:
        assert (
            await session.scalar(select(func.count()).select_from(ProductImageUnlock))
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(Message)
                .where(Message.generated_by_ai.is_(True))
            )
            == 1
        )
        raise RuntimeError("settlement storage unavailable")

    monkeypatch.setattr(
        Answers.BillingCreditService, "commit_credit_reservation", fail_settlement
    )
    with pytest.raises(ChatTypes.AnswerStorageError):
        await orchestrator.generate_answer(command)
    async with db.begin():
        run = await db.scalar(select(ProductGeneration))
        assert run.answer_metadata["phase"] == "result_ready"
        assert (
            run.answer_metadata["execution_token"]
            not in text.generate_text.await_args.args[0].request_json
        )
        staged = run.answer_metadata["content_blocks"]
        assert [b["type"] for b in staged] == ["text", "image", "text", "image"]
        assert "content_url" not in str(staged)
        assert (
            await db.scalar(select(func.count()).select_from(ProductImageUnlock)) == 0
        )
        assert (
            await db.scalar(
                select(func.count())
                .select_from(Message)
                .where(Message.generated_by_ai.is_(True))
            )
            == 0
        )
        assert await db.scalar(select(func.count()).select_from(MemoryJob)) == 0
        await db.execute(
            update(ProductGeneration).values(
                answer_lease_until=datetime.now(UTC) - timedelta(seconds=1)
            )
        )
    await check_state(
        orchestrator, command, status="pending", balance=20, reserved=10, charge=0
    )
    monkeypatch.setattr(
        Answers.BillingCreditService, "commit_credit_reservation", original
    )
    # Supervisor recovery never calls the provider; a lost successful response replays.
    assert await orchestrator.recover_answers() == 1
    first, second = await asyncio.gather(
        orchestrator.generate_answer(command), orchestrator.generate_answer(command)
    )
    assert first == second and first.status == "succeeded"
    assert text.generate_text.await_count == 1
    await check_state(
        orchestrator, command, status="succeeded", balance=10, reserved=0, charge=10
    )
    async with db.begin():
        message = await db.scalar(
            select(Message).where(Message.generated_by_ai.is_(True))
        )
        assert message.content_blocks == staged
        assert first.message_id == message.id
        unlocks = (await db.scalars(select(ProductImageUnlock))).all()
        assert (
            len(unlocks) == 1
            and str(unlocks[0].image_item_id) == selected["image_item_id"]
        )
        first_unlock = unlocks[0].unlocked_at
        assert (await db.scalar(select(MemoryJob))).requested_generation == 1
    await orchestrator.generate_answer(command)
    async with db.begin():
        assert (await db.scalar(select(ProductImageUnlock))).unlocked_at == first_unlock


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["failed", "cancelled", "stale"])
async def test_failed_cancelled_stale_never_unlock(
    db: AsyncSession, media: CharacterMediaWorkflow, failure: str
) -> None:
    orchestrator, command, text, _, _, snapshot_id = await setup_images(db, media)
    original = text.generate_text.side_effect

    async def generate(value: LLMTypes.GenerateTextCommand) -> LLMTypes.LLMResultInfo:
        if failure == "failed":
            raise RuntimeError("provider failed")
        if failure == "cancelled":
            raise asyncio.CancelledError()
        async with orchestrator.sessions() as session, session.begin():
            await session.execute(
                update(ProductSnapshot)
                .where(ProductSnapshot.id == snapshot_id)
                .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
            )
        return await original(value)

    text.generate_text.side_effect = generate
    if failure == "cancelled":
        with pytest.raises(asyncio.CancelledError):
            await orchestrator.generate_answer(command)
    answer = await orchestrator.generate_answer(command)
    assert answer.status == failure
    await check_state(
        orchestrator, command, status=failure, balance=20, reserved=0, charge=0
    )
    async with db.begin():
        assert (
            await db.scalar(select(func.count()).select_from(ProductImageUnlock)) == 0
        )
    assert text.generate_text.await_count == 1


@pytest.mark.asyncio
async def test_occurrence_http_checks_owner_revision_position_and_keeps_old_file(
    db: AsyncSession, media: CharacterMediaWorkflow
) -> None:
    orchestrator, command, _, files, selected, snapshot_id = await setup_images(
        db, media
    )
    await orchestrator.generate_answer(command)
    async with db.begin():
        page = await Messages.list_messages(
            db,
            ChatTypes.ListMessagesCommand(
                conversation_id=command.conversation_id, user_id=command.user_id
            ),
        )
        message = page.items[-1]
        response = message_info_to_response(message).model_dump(mode="json")
        url = response["content_blocks"][1]["content_url"]
        # File reading is independent of album unlock, latest version and expiry.
        from sqlalchemy import delete

        await db.execute(delete(ProductImageUnlock))
        await db.execute(
            update(ProductSnapshot)
            .where(ProductSnapshot.id == snapshot_id)
            .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
    app = FastAPI()
    app.include_router(media_router)
    actor = command.user_id

    async def owner() -> UUID:
        return actor

    async def session() -> AsyncIterator[AsyncSession]:
        async with orchestrator.sessions() as value:
            yield value

    app.dependency_overrides[dependencies.get_current_owner_id] = owner
    app.dependency_overrides[dependencies.get_product_session] = session
    app.state.product_file_version_workflow = files
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        opened = await client.get(url)
        assert opened.status_code == 200 and opened.content == b"original answer image"
        assert opened.headers["cache-control"] == "private, no-store"
        assert (
            await client.get(url.replace("/blocks/1/", "/blocks/0/"))
        ).status_code == 404
        assert (
            await client.get(url.replace("/blocks/1/", "/blocks/-1/"))
        ).status_code == 404
        assert (
            await client.get(url.replace("/revisions/1/", "/revisions/2/"))
        ).status_code == 404
        actor = uuid4()
        assert (await client.get(url)).status_code == 404
        actor = command.user_id
        await ChatService.rewind_messages(
            db,
            ChatTypes.RewindMessagesCommand(
                conversation_id=command.conversation_id,
                user_id=command.user_id,
                message_id=message.id,
            ),
        )
        assert (await client.get(url)).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["result_ready", "succeeded"])
async def test_lost_image_commit_ack_reconciles_without_duplicates(
    db: AsyncSession,
    media: CharacterMediaWorkflow,
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
) -> None:
    from contextlib import asynccontextmanager

    from app.db.transaction import use_case_transaction
    from app.modules.chatting.chat.service.command import generation as Generation

    orchestrator, command, text, _, _, _ = await setup_images(db, media)
    injected = False

    @asynccontextmanager
    async def lose_ack(session: AsyncSession) -> AsyncIterator[None]:
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
                    and run.answer_metadata.get("phase") == phase
                )
        if lost:
            injected = True
            raise RuntimeError("committed but acknowledgement lost")

    monkeypatch.setattr(Generation, "use_case_transaction", lose_ack)
    answer = await orchestrator.generate_answer(command)
    assert injected and answer.status == "succeeded"
    assert await orchestrator.generate_answer(command) == answer
    await check_state(
        orchestrator, command, status="succeeded", balance=10, reserved=0, charge=10
    )
    async with db.begin():
        assert (
            await db.scalar(select(func.count()).select_from(ProductImageUnlock)) == 1
        )
        assert (await db.scalar(select(MemoryJob))).requested_generation == 1
    assert text.generate_text.await_count == 1


@pytest.mark.asyncio
async def test_text_correction_removes_old_occurrence_but_preserves_unlock(
    db: AsyncSession, media: CharacterMediaWorkflow
) -> None:
    orchestrator, command, _, _, _, _ = await setup_images(db, media)
    await orchestrator.generate_answer(command)
    async with db.begin():
        message = await db.scalar(
            select(Message).where(Message.generated_by_ai.is_(True))
        )
        message_id = message.id
    corrected = await ChatService.replace_character_message(
        db,
        ChatTypes.ReplaceCharacterMessageCommand(
            conversation_id=command.conversation_id,
            user_id=command.user_id,
            message_id=message_id,
            expected_revision=1,
            content="Corrected text",
            product_character_id=command.product_character_id,
        ),
    )
    assert corrected.revision == 2 and corrected.content_blocks is None
    async with db.begin():
        for revision in (1, 2):
            with pytest.raises(LookupError):
                await authorize_message_image_block(
                    db,
                    ChatTypes.ReadMessageBlockCommand(
                        conversation_id=command.conversation_id,
                        user_id=command.user_id,
                        message_id=message_id,
                        revision=revision,
                        block_index=1,
                    ),
                )
        assert (
            await db.scalar(select(func.count()).select_from(ProductImageUnlock)) == 1
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["alembic", "init"])
async def test_message_blocks_migration_preserves_legacy_and_refuses_loss(
    db: AsyncSession, path: str
) -> None:
    from pathlib import Path

    from alembic.config import Config
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from alembic.script import ScriptDirectory
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    root = Path(__file__).resolve().parents[3]
    scripts = ScriptDirectory.from_config(Config(str(root / "apps/api/alembic.ini")))
    revision = scripts.get_revision("0039")

    def migrate(connection: Connection, direction: str) -> None:
        with Operations.context(MigrationContext.configure(connection)):
            getattr(revision.module, direction)()

    orchestrator, command, _ = await setup_answer(db)
    async with db.begin():
        connection = await db.connection()
        await connection.run_sync(migrate, "downgrade")
        if path == "alembic":
            await connection.run_sync(migrate, "upgrade")
        else:
            for statement in (
                (root / "infra/postgres/init/029_message_content_blocks.sql")
                .read_text()
                .split(";")
            ):
                if statement.strip():
                    await db.execute(text(statement))
        row = (
            await db.execute(
                text("SELECT content, content_blocks, revision FROM messages")
            )
        ).one()
        assert (
            row.content == "선배님, 같이 갈까요?"
            and row.content_blocks is None
            and row.revision == 1
        )
        await db.execute(
            text(
                'UPDATE messages SET content_blocks = \'[{"type":"text","text":"legacy"}]\'::jsonb'
            )
        )
    with pytest.raises(DBAPIError, match="downgrade refused"):
        async with db.begin():
            await (await db.connection()).run_sync(migrate, "downgrade")
    async with db.begin():
        assert (
            await db.scalar(
                text("SELECT jsonb_array_length(content_blocks) FROM messages")
            )
            == 1
        )
