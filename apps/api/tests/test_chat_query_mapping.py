"""Offline mapping contracts; SQLite does not verify PostgreSQL locks or concurrency."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import Column, DateTime, MetaData, String, Table, Uuid, create_engine
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.chat import Message
from app.modules.chatting.chat import repository as Repository
from app.modules.chatting.chat import types as Types
from app.modules.chatting.chat.mapper import persistence as PersistenceMapper
from app.modules.chatting.chat.mapper import prompts as PromptsPersistenceMapper
from app.modules.chatting.chat.mapper.schema import messages as MessagesSchemaMapper


def test_message_page_cursor_and_memory_source_preserve_same_snapshot() -> None:
    conversation_id = uuid4()
    now = datetime(2026, 10, 26)
    messages = [
        Message(
            id=uuid4(),
            conversation_id=conversation_id,
            sender_type="user",
            content=f"message {position}",
            position=position,
            revision=2,
            created_at=now,
            character_id=None,
            product_character_id=None,
            product_snapshot_id=None,
            generation_id=None,
            generated_by_ai=False,
            model_id=None,
        )
        for position in (11, 25, 40)
    ]
    page = PersistenceMapper.messages_entities_to_page_info(
        messages, conversation_id, 2
    )
    source = PersistenceMapper.messages_entities_to_memory_source_info(messages, 2)
    assert source.messages == page.items and source.truncated
    assert [item.position for item in page.items] == [11, 25]
    response = MessagesSchemaMapper.message_page_info_to_response(page)
    command = MessagesSchemaMapper.list_messages_request_to_command(
        conversation_id, uuid4(), response.next_cursor, 2
    )
    assert command.cursor == Types.MessageCursor(conversation_id, 25)
    assert response.items[0].content == "message 11"
    assert response.items[0].revision == 2
    messages[0].content = "changed after mapping"
    assert page.items[0].content == "message 11"
    assert PersistenceMapper.message_entity_to_info(None) is None
    assert (
        PersistenceMapper.messages_entities_to_page_info([], conversation_id, 2).items
        == ()
    )
    assert (
        PersistenceMapper.messages_entities_to_page_info(
            messages[:2], conversation_id, 2
        ).next_cursor
        is None
    )
    assert not PersistenceMapper.messages_entities_to_memory_source_info(
        messages[:2], 2
    ).truncated


def test_generation_statistics_keep_public_tuple_shapes_and_missing_status_zeros() -> (
    None
):
    snapshot_id, user_id = uuid4(), uuid4()
    facts = PersistenceMapper.generation_statistics_rows_to_info(
        ([(snapshot_id, "succeeded", 2, 5)], [(snapshot_id, user_id)])
    )
    assert facts == Types.GenerationStatisticsInfo(
        generations=[(snapshot_id, "succeeded", 2, 5)],
        users=[(snapshot_id, user_id)],
    )
    counts = PersistenceMapper.account_generation_statistics_rows_to_info(
        [("succeeded", 2), ("failed", 1)]
    )
    assert counts == Types.AccountGenerationStatisticsInfo(
        pending=0, succeeded=2, failed=1, cancelled=0, stale=0
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("recorded", [False, True])
async def test_prompt_projection_maps_real_sql_rows_and_absent_prompt(
    recorded: bool,
) -> None:
    # Minimal tables deliberately have no raw prompt or answer_metadata columns.
    # Execute the production projection to check its column order and OUTER JOIN values.
    metadata = MetaData()
    generations = Table(
        "product_generations",
        metadata,
        Column("id", Uuid, primary_key=True),
        Column("conversation_id", Uuid),
        Column("model_id", Uuid),
        Column("model_name", String),
        Column("reasoning_effort", String),
        Column("status", String),
        Column("created_at", DateTime),
        Column("finished_at", DateTime),
        Column("history_invalidated_at", DateTime),
    )
    prompts = Table(
        "generation_prompts",
        metadata,
        Column("generation_id", Uuid, primary_key=True),
        Column("created_at", DateTime),
        Column("provider", String),
    )
    engine = create_engine("sqlite://")
    try:
        metadata.create_all(engine)
        with engine.begin() as connection:
            generation_id, conversation_id, model_id = uuid4(), uuid4(), uuid4()
            created_at = datetime(2026, 10, 26, 10)
            finished_at = created_at + timedelta(minutes=2)
            prompt_created_at = created_at + timedelta(seconds=1)
            connection.execute(
                generations.insert().values(
                    id=generation_id,
                    conversation_id=conversation_id,
                    model_id=model_id,
                    model_name="stored-model",
                    reasoning_effort="high",
                    status="succeeded",
                    created_at=created_at,
                    finished_at=finished_at,
                    history_invalidated_at=None,
                )
            )
            if recorded:
                connection.execute(
                    prompts.insert().values(
                        generation_id=generation_id,
                        created_at=prompt_created_at,
                        provider="mock",
                    )
                )
            session = AsyncMock(spec=AsyncSession)
            session.execute.side_effect = connection.execute
            session.scalar.side_effect = connection.scalar
            rows, total = await Repository.list_generation_prompts(
                session,
                start=created_at,
                end=created_at + timedelta(days=1),
                conversation_id=conversation_id,
                status="succeeded",
                limit=10,
                offset=0,
            )
            page = PromptsPersistenceMapper.generation_prompt_rows_to_page(rows, total)
            expected = Types.GenerationPromptSummaryInfo(
                generation_id=generation_id,
                conversation_id=conversation_id,
                model_id=model_id,
                model_name="stored-model",
                reasoning_effort="high",
                status="succeeded",
                created_at=created_at,
                finished_at=finished_at,
                history_invalidated_at=None,
                prompt_recorded=recorded,
                prompt_created_at=prompt_created_at if recorded else None,
                provider="mock" if recorded else None,
            )
            assert page == Types.GenerationPromptPageInfo(items=(expected,), total=1)
            row = await Repository.get_generation_prompt_summary(session, generation_id)
            assert (
                PromptsPersistenceMapper.generation_prompt_row_to_summary(row)
                == expected
            )
            assert (
                await Repository.get_generation_prompt_summary(session, uuid4()) is None
            )
            assert (
                PromptsPersistenceMapper.generation_prompt_row_to_summary(None) is None
            )
            empty_rows, empty_total = await Repository.list_generation_prompts(
                session,
                start=created_at,
                end=created_at + timedelta(days=1),
                conversation_id=uuid4(),
                status=None,
                limit=10,
                offset=0,
            )
            assert PromptsPersistenceMapper.generation_prompt_rows_to_page(
                empty_rows, empty_total
            ) == Types.GenerationPromptPageInfo(items=(), total=0)
    finally:
        engine.dispose()
