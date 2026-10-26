"""Real PostgreSQL/HTTP checks for server scopes, release retries and snapshot preservation."""

import base64
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from app.db.models.chat import Conversation, Message
from app.db.models.credit import CreditTransaction
from app.db.models.product import Product
from app.modules.chatting.conversation import types as ConversationTypes
from app.modules.chatting.prompt.service import build_prompt
from app.modules.content.lorebook.service.activation import diagnose_entries
from credit_support import fund_credit
from httpx import ASGITransport, AsyncClient
from sqlalchemy import update
from test_first_answer_integration import (  # noqa: F401
    first_answer_app,
    request,
    signup_and_login,
)
from test_identity_security import auth_settings  # noqa: F401
from test_studio_publication import document


def advanced_entry(**overrides):
    """A minimal opt-in snapshot entry, independent of studio serialization."""
    value = {"id": str(uuid4()), "title": "Library", "content": "x", "entry_type": "world", "activation_type": "keyword", "is_enabled": True, "key_triggers": ["도서관", "Library"], "match_mode": "contains", "priority": 50, "token_budget": 500, "placement": "before_history", "metadata": {"activation_options": {"version": 1, "match": "all", "scan_depth": 2, "search_target": "user", "partial_match": False, "case_sensitive": True, "order": 10, "exclusive_group": ""}}}
    return {**value, **overrides}


def test_server_lore_scope_case_whole_word_and_all_keywords():
    """Speaker filtering follows depth slicing and matches can span eligible messages."""
    entry = advanced_entry()
    messages = (("user", "도서관"), ("character", "Library"), ("user", "Library"))
    assert not diagnose_entries([entry], messages=messages)[0]
    entry["metadata"]["activation_options"]["scan_depth"] = 3
    assert diagnose_entries([entry], messages=messages)[0] == [entry]
    assert not diagnose_entries([entry], messages=(("user", "도서관장 Library"),))[0]
    assert not diagnose_entries([entry], messages=(("user", "도서관 library"),))[0]
    assert diagnose_entries([entry], messages=(("user", "도서관! Library"),))[0] == [entry]


def test_server_lore_group_budget_manual_and_legacy_compatibility():
    """An over-budget winner does not reserve a group; legacy budgets remain unchanged."""
    first = advanced_entry(activation_type="always", content="한글", token_budget=1, priority=100)
    second = advanced_entry(activation_type="always", priority=75)
    for entry in (first, second):
        entry["metadata"]["activation_options"]["exclusive_group"] = "night"
    manual = advanced_entry(activation_type="manual")
    active, diagnostics = diagnose_entries([first, second, manual], manual_entry_ids=(manual["id"],))
    assert [entry["id"] for entry in active] == [second["id"], manual["id"]]
    assert diagnostics[0]["reason"] == "entry_budget_exceeded"
    legacy = advanced_entry(activation_type="always", metadata={}, token_budget=0)
    assert diagnose_entries([legacy])[0] == [legacy]
    with pytest.raises(ValueError, match="outside"):
        diagnose_entries([manual], manual_entry_ids=(str(uuid4()),))


async def save_and_publish(client, env, value, pid=None):
    """Create one saved studio revision and use the real composed release workflow."""
    pid = pid or str(uuid4())
    draft = await request(client, "PUT", f"/products/{pid}/studio-draft", json={"document": value})
    body = {"expected_revision": draft["revision"], "model_id": env.model_id, "reasoning_effort": "low", "summary": "Release", "body": "Ready"}
    release = await request(client, "POST", f"/products/{pid}/studio-publication", json=body)
    return pid, draft, body, release


@pytest.mark.asyncio
async def test_followup_release_conflicts_receipts_media_and_initial_scene(first_answer_app, monkeypatch):  # noqa: F811
    """Exercise lost-response retries, owner isolation, real file upload and old conversations."""
    env = first_answer_app
    async with AsyncClient(transport=ASGITransport(app=env.app), base_url="https://testserver") as client:
        user = await signup_and_login(client, env.mailer)
        value = document()
        value["scenes"].append({**value["scenes"][0], "id": "alternate", "title": "Other", "opening": "Different opening", "language": "English", "storyTime": "dawn", "perspective": "1인칭", "variants": "quiet"})
        value["lorebooks"].append({"id": "manual", "title": "Secret", "content": "manual secret", "activation": "manual", "enabled": True, "tokenBudget": 100})
        pid, initial_draft, first_body, first = await save_and_publish(client, env, value)
        retry = await request(client, "POST", f"/products/{pid}/studio-publication", json=first_body)
        assert retry == first
        await request(client, "POST", f"/products/{pid}/studio-publication", 409, json={**first_body, "summary": "Different request"})
        published = await request(client, "GET", f"/products/{pid}")
        conversation = await request(client, "POST", "/conversations", 201, json={"product_id": pid, "start_set_id": published["start_options"][1]["id"]})
        cid = conversation["id"]
        start = await request(client, "GET", f"/conversations/{cid}/start")
        assert start["opening_message"] == "Different opening"
        assert "English" in start["start"]["content"] and "dawn" in start["start"]["content"]
        assert "Different opening" not in start["start"]["content"]
        previous_composition = await request(client, "GET", f"/products/{pid}/composition")
        revised = deepcopy(value)
        revised["work"]["title"] = "Edited privately"
        revised["work"]["visibility"] = "전체 공개"
        revised["characters"][0]["persona"] = "Changed persona"
        saved = await request(client, "PUT", f"/products/{pid}/studio-draft", json={"expected_revision": initial_draft["revision"], "document": revised})
        assert (await request(client, "GET", f"/products/{pid}"))["title"] == "Story"
        await request(client, "PUT", f"/products/{pid}/studio-draft", 409, json={"expected_revision": initial_draft["revision"], "document": value})
        prepared = await request(client, "POST", f"/products/{pid}/studio-components", json={"expected_revision": saved["revision"]})
        character_id = prepared["characters"]["hero"]
        assert prepared == await request(client, "POST", f"/products/{pid}/studio-components", json={"expected_revision": saved["revision"]})
        image = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=")
        upload_headers = {"Content-Type": "image/png", "Idempotency-Key": str(uuid4()), "X-Filename": "test.png", "X-Media-Purpose": "studio:image:portrait"}
        await request(client, "POST", f"/characters/{character_id}/media/uploads", 422, content=b"", headers=upload_headers)
        from app.modules.asset_storage.types import AssetStorageError
        storage = env.app.state.character_media_service.storage
        original_store = storage.store_asset
        failed = False

        async def fail_once(command):
            """Inject a storage outage after the durable upload intent is committed."""
            nonlocal failed
            if not failed:
                failed = True
                raise AssetStorageError("Synthetic storage outage", kind="test_local", operation="store", object_key=command.object_key)
            return await original_store(command)

        monkeypatch.setattr(storage, "store_asset", fail_once)
        await request(client, "POST", f"/characters/{character_id}/media/uploads", 503, content=image, headers=upload_headers)
        # A rejected validation does not consume the upload idempotency key.
        media = await request(client, "POST", f"/characters/{character_id}/media/uploads", 201, content=image, headers=upload_headers)
        assert media == await request(client, "POST", f"/characters/{character_id}/media/uploads", 201, content=image, headers=upload_headers)
        revised["characters"][0]["assets"] = [{"id": "image", "name": "test.png", "usage": "portrait", "mediaId": media["media_id"]}]
        saved = await request(client, "PUT", f"/products/{pid}/studio-draft", json={"expected_revision": saved["revision"], "document": revised})
        second_body = {**first_body, "expected_revision": saved["revision"], "summary": "Update"}
        second = await request(client, "POST", f"/products/{pid}/studio-publication", json=second_body)
        assert second["version"] == 2 and second["snapshot_id"] != first["snapshot_id"]
        assert (await request(client, "GET", f"/products/{pid}/composition"))["characters"] == previous_composition["characters"]
        assert await request(client, "POST", f"/products/{pid}/studio-publication", json=first_body) == first
        assert (await request(client, "GET", f"/conversations/{cid}/start"))["opening_message"] == "Different opening"
        body = await client.get(f"/products/{pid}/versions/{second['snapshot_id']}/media/{media['media_id']}/content")
        assert body.status_code == 200 and body.content == image
        choices = await request(client, "GET", f"/conversations/{cid}/manual-lore")
        assert len(choices["items"]) == 1
        async with env.app.state.session_factory() as session, session.begin():
            await fund_credit(session, UUID(user["id"]), 100)
        message = await request(client, "POST", f"/conversations/{cid}/messages", 201, json={"request_key": "input", "content": "hello"})
        answer_body = {"request_key": "manual-answer", "input_message_id": message["id"], "expected_revision": message["revision"], "product_character_id": start["primary_product_character_id"], "manual_entry_ids": [choices["items"][0]["id"]]}
        answer = await request(client, "POST", f"/conversations/{cid}/answers", json=answer_body)
        assert answer["status"] == "succeeded"
        import json
        assert "manual secret" in json.dumps(env.llm.await_args.kwargs, ensure_ascii=False, default=str)
        await request(client, "POST", f"/conversations/{cid}/answers", 409, json={**answer_body, "manual_entry_ids": []})
        async with AsyncClient(transport=ASGITransport(app=env.app), base_url="https://testserver") as other:
            await signup_and_login(other, env.mailer)
            await request(other, "GET", f"/products/{pid}/studio-draft", 404)
            await request(other, "GET", f"/conversations/{cid}/manual-lore", 404)
            await request(other, "POST", f"/products/{pid}/studio-publication", 404, json=second_body)


@pytest.mark.asyncio
async def test_search_tags_counts_and_activity_cursors_apply_before_pages(first_answer_app):  # noqa: F811
    """Equal timestamps, nonmatching drafts and old rooms with new messages expose page bugs."""
    env = first_answer_app
    async with AsyncClient(transport=ASGITransport(app=env.app), base_url="https://testserver") as client:
        user = await signup_and_login(client, env.mailer)
        pids = []
        for index in range(3):
            value = document()
            value["work"].update(title=f"Story {index}", introduction="search needle" if index != 1 else "other", visibility="전체 공개", tags=["actual-tag"] if index != 1 else ["other"])
            pid, _, _, _ = await save_and_publish(client, env, value)
            pids.append(pid)
        stamp = datetime(2026, 10, 1, tzinfo=UTC)
        async with env.app.state.session_factory() as session, session.begin():
            await session.execute(update(Product).where(Product.id.in_(list(map(UUID, pids)))).values(created_at=stamp, status="approved"))
        tags = await request(client, "GET", "/products/catalog-tags")
        tag_id = next(tag["id"] for tag in tags if tag["name"] == "actual-tag")
        page = await request(client, "GET", "/products/catalog", params={"search": "needle", "tag_id": tag_id, "limit": 1})
        next_page = await request(client, "GET", "/products/catalog", params={"search": "needle", "tag_id": tag_id, "limit": 1, "cursor_created_at": page["next_cursor_created_at"], "cursor_id": page["next_cursor_id"]})
        assert {row["id"] for row in page["items"] + next_page["items"]} == {pids[0], pids[2]}
        assert next_page["next_cursor_id"] is None
        assert (await request(client, "GET", "/products/mine/count", params={"search": "needle"}))["total"] == 2
        assert len(await request(client, "GET", "/products/mine", params={"search": "needle", "offset": 1, "limit": 1})) == 1
        assert not (await request(client, "GET", "/products/catalog", params={"search": "%"}))["items"]
        rooms = []
        for pid in pids:
            published = await request(client, "GET", f"/products/{pid}")
            rooms.append(await request(client, "POST", "/conversations", 201, json={"product_id": pid, "start_set_id": published["start_options"][0]["id"]}))
        for room in rooms[:2]:
            await request(client, "POST", f"/conversations/{room['id']}/messages", 201, json={"request_key": "first", "content": "recent"})
        async with env.app.state.session_factory() as session, session.begin():
            await session.execute(update(Conversation).where(Conversation.user_id == UUID(user["id"])).values(created_at=stamp))
            await session.execute(update(Message).where(Message.conversation_id.in_([UUID(room["id"]) for room in rooms[:2]])).values(created_at=stamp + timedelta(days=1)))
        ids, cursor = [], {}
        while True:
            page = await request(client, "GET", "/conversations/mine", params={"limit": 1, **cursor})
            assert page["total"] == 3
            ids += [row["id"] for row in page["items"]]
            if page["next_cursor_id"] is None:
                break
            cursor = {"cursor_created_at": page["next_cursor_created_at"], "cursor_id": page["next_cursor_id"]}
        assert len(set(ids)) == 3 and ids[-1] == rooms[2]["id"]
        assert (await request(client, "GET", "/account/overview-counts")) == {"conversations": 3, "products": 3}


@pytest.mark.asyncio
async def test_ledger_signed_filter_keeps_all_operations_currency_and_ties(first_answer_app):  # noqa: F811
    """Refund/adjustment reasons follow signed deltas; unclassified legacy currency is excluded."""
    env = first_answer_app
    async with AsyncClient(transport=ASGITransport(app=env.app), base_url="https://testserver") as client:
        user = await signup_and_login(client, env.mailer)
        stamp = datetime(2026, 10, 1, tzinfo=UTC)
        async with env.app.state.session_factory() as session, session.begin():
            await fund_credit(session, UUID(user["id"]), 0)
            for operation, reason, amount in (("consume", "chat_usage", -1), ("grant", "refund", 2), ("consume", "adjustment", -3), ("grant", "adjustment", 4), ("consume", "zero_settlement", 0)):
                session.add(CreditTransaction(user_id=UUID(user["id"]), currency_code="CREDIT", operation=operation, amount=amount, namespace="fixture", reason=reason, reference_id=uuid4(), request_key=uuid4(), idempotency_key=str(uuid4()), created_at=stamp))
            session.add(CreditTransaction(user_id=UUID(user["id"]), currency_code=None, operation="legacy", amount=99, reason="legacy", idempotency_key=str(uuid4()), created_at=stamp))
        for direction, expected in (("usage", {-1, -3}), ("acquisition", {2, 4})):
            values, cursor = [], {}
            while True:
                page = await request(client, "GET", "/account/credits/transactions", params=dict(direction=direction, limit=1, **cursor))
                values += [row["amount"] for row in page["items"]]
                assert all("namespace" not in row and "reference_id" not in row for row in page["items"])
                if not page["next_cursor_id"]:
                    break
                cursor = {"cursor_created_at": page["next_cursor_created_at"], "cursor_id": page["next_cursor_id"]}
            assert set(values) == expected and len(values) == 2


def test_selected_lore_is_rendered_on_both_sides_of_history_without_system_promotion():
    """The actual prompt includes exactly the selected entries at their requested boundary."""
    import json

    from test_answer_prompt import prompt_command
    command = prompt_command()
    before = advanced_entry(activation_type="always", content="before-data")
    after = advanced_entry(activation_type="always", content="after-data", placement="near_user_message")
    active, diagnostics = diagnose_entries([before, after])
    command.runtime.lorebooks.append(ConversationTypes.RuntimeLorebook("book", "all", [], active))
    messages = json.loads(build_prompt(command).request_json)["messages"]
    indexes = {label: next(i for i, message in enumerate(messages) if label in message["content"]) for label in ("before-data", "after-data")}
    assert indexes["before-data"] < indexes["after-data"] < len(messages) - 1
    assert messages[indexes["before-data"] + 1]["content"] == command.recent_messages[0].content
    assert messages[indexes["after-data"] - 1]["content"] == command.recent_messages[1].content
    assert all(messages[indexes[label]]["role"] == "user" for label in indexes)
    assert [row["id"] for row in diagnostics if row["included"]] == [entry["id"] for entry in active]
