"""Disposable local browser lab. Uses only chatkit_test and a new isolated schema.

Run from the repository root with .venv/Scripts/python.exe. No .env is loaded,
external AI keys are cleared, and only the existing mock text adapter is enabled.
"""

import base64
import json
import os
import secrets
import sys
from contextlib import asynccontextmanager
from dataclasses import asdict, replace
from pathlib import Path
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "apps/api"), str(ROOT / "apps/api/tests")]

from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import create_async_engine
import uvicorn

from app import main
from app.db.base import Base
from app.db.models.model_routing import Model, Provider
from app.db.models.product import Product
from app.modules.identity.adapters import SMTPMailSender
from answer_billing_support import answer_pricing
from credit_support import fund_credit
from test_identity_auth import RecordingMailer
from test_studio_publication import document

SCHEMA = "workflow_browser_" + uuid4().hex
MODEL_ID = uuid4()
DIRECTORY = ROOT / "tmp/workflow-runtime"
DIRECTORY.mkdir(parents=True, exist_ok=True)
ORIGIN = "http://127.0.0.1:3003"
URL = "postgresql+asyncpg://chatkit:chatkit@127.0.0.1:5432/chatkit_test"
EMAIL = "workflow-browser@example.com"
PASSWORD = "Disposable workflow test 2026!"


def configure():
    """Create ephemeral auth keys and an explicitly synthetic mock pricing configuration."""
    values = dict(DATABASE_URL=URL, ENVIRONMENT="test", AUTH_JWT_KEY=base64.b64encode(secrets.token_bytes(32)).decode(), AUTH_FLOW_KEY=Fernet.generate_key().decode(), AUTH_PUBLIC_ORIGIN=ORIGIN, AUTH_SECURE_COOKIES="false", CORS_ORIGINS="", GOOGLE_CLIENT_ID="", GOOGLE_CLIENT_SECRET="", GOOGLE_CALLBACK_URL=ORIGIN + "/auth/google/callback", SMTP_HOST="localhost", SMTP_PORT="1025", SMTP_FROM="test@example.com", SMTP_TLS="none", ASSET_STORAGE_KIND="test_local", ASSET_TEST_LOCAL_ROOT=str(DIRECTORY / "assets"), LLM_PROVIDER="mock", OPENAI_API_KEY="", ANTHROPIC_API_KEY="", VOYAGE_API_KEY="", MAX_PROMPT_TOKENS="16000", MAX_RESPONSE_TOKENS="1200")
    os.environ.update(values)
    pricing = answer_pricing(MODEL_ID)
    model = pricing.price_book.models[0]
    execution = replace(model.execution, provider="mock", model="mock-workflow", reasoning_effort="none")
    price_book = replace(pricing.price_book, models=(replace(model, execution=execution),))
    path = DIRECTORY / "synthetic-prices.json"
    path.write_text(json.dumps({"price_book": asdict(price_book), "quote_ttl_seconds": 60}, default=str), encoding="utf-8")
    os.environ["BILLING_PRICING_CONFIG_PATH"] = str(path)


def scoped_engine(url, **kwargs):
    """Keep every real app session inside this run's disposable test schema."""
    if url != URL:
        raise RuntimeError("Only the explicitly named test database is allowed")
    return create_async_engine(url, connect_args={"server_settings": {"search_path": f"{SCHEMA},public"}}, **kwargs)


configure()
main.create_async_engine = scoped_engine
mailer = RecordingMailer()
SMTPMailSender.send_mail = mailer.send_mail
app = main.create_app()
original_lifespan = app.router.lifespan_context


async def call(client, method, path, expected=200, **kwargs):
    """Fail startup if real HTTP setup does not satisfy the normal contract."""
    response = await client.request(method, path, **kwargs)
    if response.status_code != expected:
        raise RuntimeError((path, response.status_code, response.text))
    return response.json() if response.content else None


@asynccontextmanager
async def lifespan(application):
    """Build only a new test schema, then seed through real cookie-authenticated APIs."""
    engine = scoped_engine(URL)
    async with engine.begin() as connection:
        await connection.execute(text(f"CREATE SCHEMA {SCHEMA}"))
        await connection.run_sync(lambda connection: Base.metadata.create_all(connection, checkfirst=False))
    await engine.dispose()
    async with original_lifespan(application):
        async with application.state.session_factory() as session, session.begin():
            provider = Provider(id=uuid4(), name="mock")
            session.add(provider)
            await session.flush()
            session.add(Model(id=MODEL_ID, provider_id=provider.id, model_name="mock-workflow", display_name="Local mock · no external AI", context_window=32000, input_price=0, output_price=0, capabilities={"reasoning_efforts": ["none"], "model_family": "mock"}))
        async with AsyncClient(transport=ASGITransport(app=application), base_url=ORIGIN, headers={"Origin": ORIGIN}) as client:
            csrf = await call(client, "GET", "/auth/csrf")
            client.headers["X-CSRF-Token"] = csrf["csrf_token"]
            await call(client, "POST", "/auth/register", 202, json={"email": EMAIL, "password": PASSWORD})
            user = await call(client, "POST", "/auth/email/verify", json={"token": mailer.token("verify")})
            await call(client, "POST", "/auth/login", json={"email": EMAIL, "password": PASSWORD})
            async with application.state.session_factory() as session, session.begin():
                await fund_credit(session, UUID(user["id"]), 500)
            pids = []
            for index in range(3):
                pid = str(uuid4())
                value = document()
                value["work"].update(title=f"검증 작품 {index + 1}", introduction="서버 검색 needle" if index != 1 else "별도 검색", visibility="전체 공개", tags=["검증 태그"] if index != 1 else ["다른 태그"])
                value["characters"][0].update(introduction="길잡이", dialogue="안녕하세요", relationships="", role="길잡이", tags=[])
                value["lorebooks"][0].update(category="세계관", folder="세계관", keywords=[], tags=[], match="any", priority="높음", scanDepth=9, searchTarget="all", partialMatch=True, caseSensitive=False, tokenBudget=800, order=100, placement="before", exclusiveGroup="")
                value["lorebooks"].append({**value["lorebooks"][0], "id": "manual", "title": "수동 비밀", "content": "테스트 수동 비밀", "activation": "manual"})
                value["scenes"][0].update(placeId="", language="한국어", storyTime="밤", perspective="2인칭", variants="")
                draft = await call(client, "PUT", f"/products/{pid}/studio-draft", json={"document": value})
                await call(client, "POST", f"/products/{pid}/studio-publication", json=dict(expected_revision=draft["revision"], model_id=str(MODEL_ID), reasoning_effort="none", summary="Local fixture", body="No external services"))
                pids.append(pid)
                published = await call(client, "GET", f"/products/{pid}")
                room = await call(client, "POST", "/conversations", 201, json={"product_id": pid, "start_set_id": published["start_options"][0]["id"]})
                if index == 0:
                    await call(client, "POST", f"/conversations/{room['id']}/messages", 201, json={"request_key": "seed-message", "content": "최근 활동을 확인해요"})
            async with application.state.session_factory() as session, session.begin():
                await session.execute(update(Product).where(Product.id.in_(list(map(UUID, pids)))).values(status="approved"))
        (DIRECTORY / "session.json").write_text(json.dumps({"schema": SCHEMA, "email": EMAIL, "password": PASSWORD, "products": pids, "model_id": str(MODEL_ID)}, ensure_ascii=False), encoding="utf-8")
        print("Disposable workflow lab ready: 127.0.0.1:8012; schema=" + SCHEMA, flush=True)
        yield


app.router.lifespan_context = lifespan
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8012, access_log=False)
