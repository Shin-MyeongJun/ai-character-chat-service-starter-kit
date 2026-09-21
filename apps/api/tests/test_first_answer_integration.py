"""Default app lifespan + real cookie auth/PostgreSQL; only mail/AI I/O is fake.

Provider/Model are the only directly inserted prerequisites: no creation API exists.
All user/content/conversation/message data is created through public HTTP APIs.
"""

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
import voyageai
from app import main
from app.db.models.billing import UsageLog
from app.db.models.chat import Conversation, Message
from app.db.models.identity import AuthSession, User
from app.db.models.memory import MemoryJob
from app.db.models.model_routing import Model, Provider
from app.db.models.product_usage import ProductGeneration
from app.modules.identity.adapters import SMTPMailSender
from httpx import ASGITransport, AsyncClient, Cookies
from openai.resources.responses import AsyncResponses
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import create_async_engine
from test_identity_auth import RecordingMailer, csrf
from test_identity_security import auth_settings  # noqa: F401

pytestmark = pytest.mark.asyncio
PASSWORD = "first-answer password 123!"
ANSWER = '"반가워요. 함께 출발해요."'


async def request(client, method, path, status=200, **kwargs):
    response = await client.request(method, path, **kwargs)
    assert response.status_code == status, (method, path, response.text)
    return response.json() if response.content else None


@pytest_asyncio.fixture
async def first_answer_app(db, auth_settings, monkeypatch, tmp_path):  # noqa: F811
    # Keep a real engine and every app-created session, scoped to conftest's UUID
    # schema. Neither authentication nor database dependencies are overridden.
    schema = await db.scalar(text("SELECT current_schema()"))
    await db.rollback()

    def isolated_engine(url, **kwargs):
        assert url == os.environ["TEST_DATABASE_URL"]
        return create_async_engine(
            url,
            connect_args={"server_settings": {"search_path": f"{schema},public"}},
            **kwargs,
        )

    monkeypatch.setattr(main, "create_async_engine", isolated_engine)
    settings = {
        "DATABASE_URL": os.environ["TEST_DATABASE_URL"],
        "ENVIRONMENT": "test",
        "AUTH_JWT_KEY": auth_settings.jwt_key,
        "AUTH_FLOW_KEY": auth_settings.flow_key,
        "AUTH_PUBLIC_ORIGIN": "https://testserver",
        "AUTH_SECURE_COOKIES": "true",
        "CORS_ORIGINS": "",
        "GOOGLE_CLIENT_ID": "",
        "GOOGLE_CLIENT_SECRET": "",
        "GOOGLE_CALLBACK_URL": "https://testserver/auth/google/callback",
        "SMTP_HOST": "localhost",
        "SMTP_FROM": "test@example.com",
        "SMTP_TLS": "none",
        "ASSET_STORAGE_KIND": "test_local",
        "ASSET_TEST_LOCAL_ROOT": str(tmp_path / "assets"),
        "LLM_PROVIDER": "openai",
        "OPENAI_API_KEY": "test-only-not-a-provider-key",
        "ANTHROPIC_API_KEY": "",
        "VOYAGE_API_KEY": "test-only-not-a-provider-key",
        "VOYAGE_EMBEDDING_MODEL": "voyage-large-2",
        "VOYAGE_EMBEDDING_OUTPUT_DIMENSION": "1536",
        "EMBEDDING_PROVIDER": "voyage",
        "MAX_PROMPT_TOKENS": "8000",
        "MAX_RESPONSE_TOKENS": "1200",
        "ANSWER_TIMEOUT_SECONDS": "90",
        "MEMORY_RETRIEVAL_TOKEN_BUDGET": "1200",
        "MEMORY_RETRIEVAL_CANDIDATES": "20",
        "MEMORY_RETRIEVAL_LIMIT": "8",
        "MEMORY_RECENT_RAW_TOKENS": "1200",
        "MEMORY_SUMMARY_THRESHOLD_TOKENS": "4000",
    }
    for name, value in settings.items():
        monkeypatch.setenv(name, value)

    mailer = RecordingMailer()
    monkeypatch.setattr(SMTPMailSender, "send_mail", mailer.send_mail)
    llm = AsyncMock(
        return_value={
            "output_text": ANSWER,
            "output": [],
            "model": "gpt-test",
            "status": "completed",
            "usage": {"input_tokens": 100, "output_tokens": 30, "total_tokens": 130},
        }
    )
    monkeypatch.setattr(AsyncResponses, "create", llm)
    embedding = AsyncMock(
        return_value=SimpleNamespace(embeddings=[[1.0] + [0.0] * 1535], total_tokens=3)
    )
    monkeypatch.setattr(voyageai.AsyncClient, "embed", embedding)

    async with db.begin():
        provider = Provider(id=uuid4(), name="openai")
        db.add(provider)
        await db.flush()
        model = Model(
            id=uuid4(),
            provider_id=provider.id,
            model_name="gpt-test",
            display_name="Deterministic integration model",
            context_window=32000,
            input_price=1,
            output_price=1,
            capabilities={"reasoning_efforts": ["low"], "model_family": "test"},
        )
        db.add(model)

    app = main.create_app()
    async with app.router.lifespan_context(app):
        async with app.state.session_factory() as session:
            assert await session.scalar(text("SELECT current_schema()")) == schema
        yield SimpleNamespace(
            app=app, mailer=mailer, llm=llm, embedding=embedding, model_id=str(model.id)
        )


async def signup_and_login(client, mailer):
    await csrf(client)
    credentials = {"email": f"{uuid4().hex}@example.com", "password": PASSWORD}
    await request(client, "POST", "/auth/register", 202, json=credentials)
    assert not client.cookies.get("__Host-chatkit_access")
    rejected = await request(client, "POST", "/auth/login", 401, json=credentials)
    assert rejected["error"]["code"] == "invalid_credentials"
    token = mailer.token("verify")
    user = await request(client, "POST", "/auth/email/verify", json={"token": token})
    assert user["email_verified"] is True
    await request(client, "POST", "/auth/email/verify", 400, json={"token": token})
    assert await request(client, "POST", "/auth/login", json=credentials) == user
    assert client.cookies.get("__Host-chatkit_access")
    assert client.cookies.get("__Host-chatkit_refresh")
    assert await request(client, "GET", "/auth/me") == user
    return user


@pytest_asyncio.fixture
async def first_chat(first_answer_app):
    env = first_answer_app
    async with AsyncClient(
        transport=ASGITransport(app=env.app), base_url="https://testserver"
    ) as client:
        user = await signup_and_login(client, env.mailer)
        character = (
            await request(
                client,
                "POST",
                "/characters",
                201,
                json={"name": "길잡이", "persona_prompt": "친절하게 여행을 안내한다."},
            )
        )["character"]
        book = (
            await request(
                client, "POST", "/lorebooks", 201, json={"title": "출발 설정"}
            )
        )["lorebook"]
        entry = (
            await request(
                client,
                "POST",
                "/lorebooks/entries",
                201,
                json={
                    "lorebook_id": book["id"],
                    "title": "광장",
                    "content": "여행자가 광장에서 길잡이를 만난다.",
                    "entry_type": "start_set",
                },
            )
        )["entry"]
        product = await request(
            client,
            "POST",
            "/products",
            201,
            json={"title": "첫 여행", "opening_message": "어서 와요, 여행자님."},
        )
        pid = product["id"]
        assert product["visibility"] == "private" and product["status"] == "draft"
        await request(
            client,
            "PUT",
            f"/products/{pid}/composition",
            json={
                "characters": [{"character_id": character["id"], "is_primary": True}],
                "lorebooks": [{"lorebook_id": book["id"], "role": "main"}],
            },
        )
        await request(
            client,
            "PUT",
            f"/products/{pid}/settings",
            json={
                "model_id": env.model_id,
                "reasoning_effort": "low",
                "start_entry_ids": [entry["id"]],
            },
        )
        release = await request(
            client,
            "POST",
            f"/products/{pid}/releases",
            201,
            json={"summary": "첫 발행", "body": "여행 시작"},
        )
        published = await request(client, "GET", f"/products/{pid}")
        conversation = await request(
            client,
            "POST",
            "/conversations",
            201,
            json={
                "product_id": pid,
                "start_set_id": published["start_options"][0]["id"],
            },
        )
        cid = conversation["id"]
        assert conversation["product_snapshot_id"] == release["snapshot_id"]
        messages_path = f"/conversations/{cid}/messages"
        opening = (await request(client, "GET", messages_path))["items"]
        assert len(opening) == 1 and not opening[0]["generated_by_ai"]
        message = await request(
            client,
            "POST",
            messages_path,
            201,
            json={"request_key": "input-1", "content": "어디로 갈까요?"},
        )
        body = {
            "request_key": "answer-1",
            "input_message_id": message["id"],
            "expected_revision": message["revision"],
            "product_character_id": opening[0]["product_character_id"],
        }
        yield SimpleNamespace(
            **vars(env),
            client=client,
            user=user,
            product_id=pid,
            cid=cid,
            snapshot_id=release["snapshot_id"],
            message=message,
            messages_path=messages_path,
            answers_path=f"/conversations/{cid}/answers",
            body=body,
        )


async def assert_persisted(chat, answer):
    # Fresh sessions observe committed data, not an HTTP handler's identity map.
    async with chat.app.state.session_factory() as session:
        user = await session.get(User, UUID(chat.user["id"]))
        assert user.email_verified and user.password_hash.startswith("$argon2id$")
        conversation = await session.get(Conversation, UUID(chat.cid))
        assert conversation.user_id == user.id
        run = (await session.scalars(select(ProductGeneration))).one()
        usage = (await session.scalars(select(UsageLog))).one()
        messages = (
            await session.scalars(select(Message).order_by(Message.position))
        ).all()
        assert len(messages) == 3  # authored opening, user input, generated answer
        assert [m.sender_type for m in messages] == ["character", "user", "character"]
        assert messages[1].id == UUID(chat.message["id"])
        assert messages[1].content == "어디로 갈까요?"
        assert messages[2].content == answer["content"] == ANSWER
        assert messages[2].generated_by_ai and not messages[1].generated_by_ai
        assert (
            run.id
            == usage.generation_id
            == messages[2].generation_id
            == UUID(answer["generation_id"])
        )
        assert run.user_id == usage.user_id == user.id
        assert run.conversation_id == usage.conversation_id == conversation.id
        assert run.product_id == usage.product_id == UUID(chat.product_id)
        assert (
            run.product_snapshot_id
            == usage.product_snapshot_id
            == messages[2].product_snapshot_id
            == UUID(chat.snapshot_id)
        )
        assert (
            run.model_id
            == usage.model_id
            == messages[2].model_id
            == UUID(chat.model_id)
        )
        assert run.status == "succeeded" and run.message_count == 1
        assert run.finished_at is not None
        assert run.answer_metadata["usage"]["input_tokens"] == usage.input_tokens == 100
        assert (
            run.answer_metadata["usage"]["output_tokens"] == usage.output_tokens == 30
        )
        assert usage.cost_credit == 0  # existing recording contract, not a price policy
        assert (
            await session.scalars(select(MemoryJob))
        ).one().requested_generation == 1


async def test_signup_to_first_answer_and_completed_replay(first_chat):
    chat = first_chat
    first = await request(chat.client, "POST", chat.answers_path, json=chat.body)
    assert first["status"] == "succeeded"
    await assert_persisted(chat, first)
    assert (
        await request(chat.client, "POST", chat.answers_path, json=chat.body) == first
    )
    await assert_persisted(chat, first)
    page = await request(chat.client, "GET", chat.messages_path)
    assert page["items"][-1]["content"] == first["content"]
    assert page["items"][-1]["generation_id"] == first["generation_id"]
    assert page["next_cursor"] is None
    await request(chat.client, "GET", f"/conversations/{chat.cid}/updates")
    chat.llm.assert_awaited_once()
    assert chat.llm.await_args.kwargs["model"] == "gpt-test"
    # A first conversation has no compatible memories; real retrieval skips embedding.
    chat.embedding.assert_not_awaited()


@pytest.mark.parametrize(
    "field", ["input_message_id", "expected_revision", "product_character_id"]
)
async def test_completed_request_key_rejects_changed_input(first_chat, field):
    chat = first_chat
    answer = await request(chat.client, "POST", chat.answers_path, json=chat.body)
    body = {**chat.body, field: 2 if field == "expected_revision" else str(uuid4())}
    await request(chat.client, "POST", chat.answers_path, 409, json=body)
    assert (
        await request(chat.client, "POST", chat.answers_path, json=chat.body) == answer
    )
    chat.llm.assert_awaited_once()
    await assert_persisted(chat, answer)


def protected_requests(chat):
    return [
        ("GET", chat.messages_path, None),
        ("GET", f"/conversations/{chat.cid}/updates", None),
        (
            "POST",
            f"/conversations/{chat.cid}/version",
            {"target_snapshot_id": chat.snapshot_id},
        ),
        (
            "PUT",
            f"{chat.messages_path}/{chat.message['id']}",
            {"content": "forged", "expected_revision": 1},
        ),
        ("DELETE", f"{chat.messages_path}/{chat.message['id']}", None),
        ("POST", chat.messages_path, {"request_key": "forged", "content": "forged"}),
        ("POST", chat.answers_path, chat.body),
    ]


async def assert_no_generation(chat):
    chat.llm.assert_not_awaited()
    chat.embedding.assert_not_awaited()
    async with chat.app.state.session_factory() as session:
        assert (
            await session.scalar(select(func.count()).select_from(ProductGeneration))
            == 0
        )
        assert await session.scalar(select(func.count()).select_from(UsageLog)) == 0
        messages = (
            await session.scalars(select(Message).order_by(Message.position))
        ).all()
        assert len(messages) == 2 and messages[-1].content == "어디로 갈까요?"


async def test_other_verified_user_cannot_access_or_change_conversation(first_chat):
    chat = first_chat
    async with AsyncClient(
        transport=ASGITransport(app=chat.app), base_url="https://testserver"
    ) as other:
        user = await signup_and_login(other, chat.mailer)
        assert user["id"] != chat.user["id"]
        await request(other, "GET", f"/products/{chat.product_id}", 404)
        await request(
            other, "POST", "/conversations", 404, json={"product_id": chat.product_id}
        )
        for method, path, body in protected_requests(chat):
            await request(other, method, path, 404, json=body)
        await assert_no_generation(chat)
        # The owner's input remains usable; completed results stay private too.
        answer = await request(chat.client, "POST", chat.answers_path, json=chat.body)
        await request(other, "GET", chat.messages_path, 404)
        await request(other, "POST", chat.answers_path, 404, json=chat.body)
    chat.llm.assert_awaited_once()
    await assert_persisted(chat, answer)


@pytest.mark.parametrize(
    "logged_out", [False, True], ids=["anonymous", "revoked-cookie"]
)
async def test_anonymous_and_logged_out_cookies_are_rejected(first_chat, logged_out):
    chat = first_chat
    cookies = Cookies(chat.client.cookies) if logged_out else Cookies()
    headers = dict(chat.client.headers) if logged_out else {}
    if logged_out:
        await request(chat.client, "POST", "/auth/logout", 204)
        assert not chat.client.cookies.get("__Host-chatkit_access")
        async with chat.app.state.session_factory() as session:
            assert (
                await session.scalars(select(AuthSession))
            ).one().revoked_at is not None
    for method, path, body in protected_requests(chat):
        # Restore old cookies for EACH request; a 401 clears the client's jar.
        async with AsyncClient(
            transport=ASGITransport(app=chat.app),
            base_url="https://testserver",
            cookies=cookies,
            headers=headers,
        ) as denied:
            if not logged_out:
                # Valid CSRF, but no access/refresh cookie: reach real auth.
                await csrf(denied)
            response = await request(denied, method, path, 401, json=body)
            assert response["error"]["code"] in {"invalid_token", "invalid_session"}
    await assert_no_generation(chat)


@pytest.mark.parametrize("kind", ["missing", "mismatch", "origin"])
async def test_csrf_rejects_authenticated_mutations(first_chat, kind):
    chat = first_chat
    headers = dict(chat.client.headers)
    if kind == "missing":
        del headers["x-csrf-token"]
    elif kind == "mismatch":
        headers["x-csrf-token"] = "not-the-cookie"
    else:
        headers["origin"] = "https://untrusted.example"
    async with AsyncClient(
        transport=ASGITransport(app=chat.app),
        base_url="https://testserver",
        cookies=chat.client.cookies,
        headers=headers,
    ) as denied:
        for method, path, body in protected_requests(chat):
            if method == "GET":
                continue
            error = await request(denied, method, path, 403, json=body)
            assert error["error"]["code"] == (
                "origin_forbidden" if kind == "origin" else "csrf_failed"
            )
    await assert_no_generation(chat)
    answer = await request(chat.client, "POST", chat.answers_path, json=chat.body)
    await assert_persisted(chat, answer)
