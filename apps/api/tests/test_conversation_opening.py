"""Fixed starts have no message identity; legacy histories are preserved explicitly."""

import json
import runpy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from app.db.models.chat import Conversation, Message
from app.db.models.product import Product
from app.db.models.snapshot.product import ProductSnapshot
from app.db.transaction import use_case_transaction
from app.http.dependencies import get_current_owner_id, get_product_session
from app.modules.chatting.chat import types as ChatTypes
from app.modules.chatting.chat.mapper.prompt import message_info_to_prompt
from app.modules.chatting.chat.service.command import messages as MessagesCommandService
from app.modules.chatting.chat.service.query import messages as MessagesQueryService
from app.modules.chatting.conversation import types as Types
from app.modules.chatting.conversation.router import router
from app.modules.chatting.conversation.service.command.context import (
    prepare_runtime_context,
)
from app.modules.chatting.conversation.service.command.versions import switch_version
from app.modules.chatting.conversation.service.views import get_conversation_start
from app.modules.chatting.prompt import service as PromptService
from app.modules.chatting.prompt import types as PromptTypes
from app.modules.content.product import types as ProductTypes
from app.modules.content.product.service.command.releases import publish_product
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from test_product_usage import scenario

pytestmark = pytest.mark.asyncio


async def test_new_start_is_separate_authorized_http_content_and_not_memory_source(db):
    owner, _, release, cid, character = await scenario(db)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_owner_id] = lambda: owner.id

    async def session():
        yield db

    app.dependency_overrides[get_product_session] = session
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(f"/conversations/{cid}/start")
        assert response.status_code == 200
        value = response.json()
        assert value["opening_mode"] == "snapshot"
        assert value["opening_message"] == "Hello"
        assert value["initial_snapshot_id"] == str(release.snapshot_id)
        assert value["start"]["content"] == "Begin at home"
        assert value["primary_product_character_id"] == str(character)
        assert value["participants"][0]["product_character_id"] == str(character)
        assert "message_id" not in value and "id" not in value
        source = await MessagesQueryService.list_memory_source(
            db, ChatTypes.ListMemorySourceCommand(conversation_id=cid, user_id=owner.id)
        )
        assert source.messages == ()
        assert (
            list(
                await db.scalars(select(Message).where(Message.conversation_id == cid))
            )
            == []
        )
        await db.rollback()
        app.dependency_overrides[get_current_owner_id] = uuid4
        denied = await client.get(f"/conversations/{cid}/start")
        assert denied.status_code == 404


async def test_version_switch_uses_current_characters_but_initial_opening_and_start(db):
    owner, product, first, cid, character = await scenario(db)
    async with use_case_transaction(db):
        stored_product = await db.get(Product, product.id)
        stored_product.opening_message = "A different version opening"
    latest = await publish_product(
        db,
        ProductTypes.PublishCommand(
            product_id=product.id,
            owner_id=owner.id,
            value=ProductTypes.ReleaseNoteCommand("Next", "Opening changed"),
        ),
    )
    await switch_version(
        db,
        Types.SwitchVersionCommand(
            conversation_id=cid, user_id=owner.id, target_snapshot_id=latest.snapshot_id
        ),
    )
    async with use_case_transaction(db):
        initial = await db.get(ProductSnapshot, first.snapshot_id)
        initial.expires_at = datetime.now(UTC) - timedelta(days=1)
    runtime = await prepare_runtime_context(
        db, Types.PrepareRuntimeContextCommand(conversation_id=cid, user_id=owner.id)
    )
    assert runtime.product_snapshot_id == str(latest.snapshot_id)
    assert runtime.opening_message == "Hello"
    assert runtime.start.content == "Begin at home"
    assert "opening_message" not in runtime.settings
    async with db.begin():
        start = await get_conversation_start(
            db, Types.OwnedConversationCommand(conversation_id=cid, user_id=owner.id)
        )
    assert start.initial_snapshot_id == first.snapshot_id
    assert start.primary_product_character_id != character
    assert start.primary_product_character_id in {
        p.product_character_id for p in start.participants
    }


@pytest.mark.parametrize("legacy", [False, True])
async def test_prompt_does_not_duplicate_opening_or_remove_matching_user_text(
    db, legacy
):
    owner, _, _, cid, character = await scenario(db)
    if legacy:
        async with use_case_transaction(db):
            conversation = await db.get(Conversation, cid)
            conversation.opening_mode = "legacy_messages"
        # Legacy content may have been edited; it must not be classified by text.
        old = await MessagesCommandService.create_character_message(
            db,
            ChatTypes.CreateCharacterMessageCommand(
                conversation_id=cid,
                user_id=owner.id,
                request_key="opening",
                content="Edited legacy opening",
                product_character_id=character,
            ),
        )
    current = await MessagesCommandService.create_message(
        db,
        ChatTypes.CreateMessageCommand(
            conversation_id=cid,
            user_id=owner.id,
            request_key="input",
            content="Hello",
        ),
    )
    runtime = await prepare_runtime_context(
        db, Types.PrepareRuntimeContextCommand(conversation_id=cid, user_id=owner.id)
    )
    async with db.begin():
        source = await MessagesQueryService.list_memory_source(
            db, ChatTypes.ListMemorySourceCommand(conversation_id=cid, user_id=owner.id)
        )
    command = PromptTypes.BuildPromptCommand(
        template=PromptService.load_template(),
        runtime=runtime,
        product_character_id=character,
        current_message=message_info_to_prompt(current),
        recent_messages=tuple(message_info_to_prompt(m) for m in source.messages),
    )
    messages = json.loads(PromptService.build_prompt(command).request_json)["messages"]
    assert messages[-1] == {"role": "user", "content": "Hello"}
    assistants = [m["content"] for m in messages if m["role"] == "assistant"]
    assert assistants == ["Edited legacy opening" if legacy else "Hello"]
    if legacy:
        assert runtime.opening_message is None
        assert source.messages[0].id == old.id
    else:
        # Fixed context remains even if every optional older turn is dropped.
        assert (
            json.loads(
                PromptService.build_prompt(
                    replace(command, recent_messages=())
                ).request_json
            )["messages"]
            == messages
        )


async def test_legacy_without_verified_snapshot_does_not_invent_start_content(db):
    owner, _, _, cid, _ = await scenario(db)
    async with use_case_transaction(db):
        conversation = await db.get(Conversation, cid)
        conversation.product_snapshot_id = None
        conversation.initial_snapshot_id = None
        conversation.start_set_id = None
        conversation.opening_mode = "legacy_messages"
    async with db.begin():
        result = await get_conversation_start(
            db, Types.OwnedConversationCommand(conversation_id=cid, user_id=owner.id)
        )
    assert result.opening_message is None and result.start is None
    assert result.primary_product_character_id is None


async def test_downgrade_rejects_loss_of_fixed_start_contract(db):
    _, _, _, cid, _ = await scenario(db)
    migration = runpy.run_path(
        str(Path(__file__).parents[1] / "alembic/versions/0025_conversation_opening.py")
    )

    def downgrade(connection):
        with Operations.context(MigrationContext.configure(connection)):
            migration["downgrade"]()

    with pytest.raises(DBAPIError, match="Preserve fixed opening contract"):
        async with db.begin():
            connection = await db.connection()
            await connection.run_sync(downgrade)
    async with db.begin():
        assert (await db.get(Conversation, cid)).opening_mode == "snapshot"
