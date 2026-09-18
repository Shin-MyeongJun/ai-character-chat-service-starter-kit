"""선택 실행: 로컬 Mailpit SMTP로 받은 실제 인증/재설정 링크를 HTTP API에서 사용한다."""

import os
import re
from dataclasses import replace
from uuid import uuid4

import pytest
from app.modules.identity.adapters import SMTPMailSender
from httpx import AsyncClient
from test_identity_auth import (  # noqa: F401
    PASSWORD,
    auth_http,
    csrf,
    identity_db,
    login,
)
from test_identity_security import auth_settings  # noqa: F401


@pytest.mark.asyncio
async def test_mailpit_real_smtp_verification_and_reset(auth_http):  # noqa: F811
    url = os.getenv("TEST_MAILPIT_HTTP_URL")
    if not url:
        pytest.skip("TEST_MAILPIT_HTTP_URL required for real local SMTP verification")
    client, auth, _, _, _ = auth_http
    settings = replace(
        auth.settings,
        smtp_host="127.0.0.1",
        smtp_port=int(os.getenv("TEST_MAILPIT_SMTP_PORT", "1025")),
    )
    auth.mailer = SMTPMailSender(settings)
    email = f"auth-{uuid4().hex}@example.com"

    async def read_token(subject):
        # 임의 메일함 삭제 없이 이번 테스트의 수신 주소만 검색한다.
        async with AsyncClient(base_url=url, timeout=10) as mailbox:
            response = await mailbox.get(
                "/api/v1/search", params={"query": f"to:{email}"}
            )
            response.raise_for_status()
            message = next(
                m for m in response.json()["messages"] if m["Subject"] == subject
            )
            detail = await mailbox.get("/api/v1/message/" + message["ID"])
            detail.raise_for_status()
            content = detail.json()["Text"]
            assert PASSWORD not in content
            return re.search(r"#token=([A-Za-z0-9_-]+)", content).group(1)

    assert (
        await client.post("/auth/register", json={"email": email, "password": PASSWORD})
    ).status_code == 202
    verify = await read_token("이메일 인증")
    assert (
        await client.post("/auth/email/verify", json={"token": verify})
    ).status_code == 200
    assert (await login(client, email=email)).status_code == 200
    assert (
        await client.post("/auth/password/reset/request", json={"email": email})
    ).status_code == 202
    reset = await read_token("비밀번호 재설정")
    assert (
        await client.post(
            "/auth/password/reset", json={"token": reset, "password": PASSWORD + "new"}
        )
    ).status_code == 204
    await csrf(client)
    assert (
        await login(client, email=email, password=PASSWORD + "new")
    ).status_code == 200
