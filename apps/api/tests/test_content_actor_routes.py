"""Actor separation must keep the original authorization dependencies and paths."""

from unittest.mock import AsyncMock
from uuid import uuid4

from app.http.routes import router
from app.modules.content.character import dependencies as CharacterDependencies
from app.modules.content.character.service import command as CharacterCommandService
from app.modules.content.lorebook import dependencies as LorebookDependencies
from app.modules.content.lorebook import types as LorebookTypes
from app.modules.content.lorebook.service import query as LorebookQueryService
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient


def deny_access():
    raise HTTPException(status_code=403, detail="Denied by actor guard")


def test_owner_path_is_not_captured_by_admin_uuid_path(monkeypatch):
    owner_id = uuid4()
    session = object()
    own_query = AsyncMock(return_value=LorebookTypes.LorebookPage([], None))
    admin_query = AsyncMock()
    monkeypatch.setattr(LorebookQueryService, "list_lorebooks_by_owner_id", own_query)
    monkeypatch.setattr(LorebookQueryService, "list_lorebooks", admin_query)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides.update(
        {
            LorebookDependencies.get_current_owner_id: lambda: owner_id,
            LorebookDependencies.get_lorebook_session: lambda: session,
            LorebookDependencies.require_lorebook_admin: deny_access,
        }
    )
    with TestClient(app) as client:
        assert client.get("/lorebooks/me").status_code == 200
        assert client.get("/lorebooks").status_code == 403
    assert own_query.await_args.args[1].owner_id == owner_id
    admin_query.assert_not_awaited()


def test_moderation_guard_prevents_status_mutation(monkeypatch):
    change = AsyncMock()
    monkeypatch.setattr(CharacterCommandService, "change_character_status", change)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides.update(
        {
            CharacterDependencies.get_current_owner_id: uuid4,
            CharacterDependencies.get_character_session: lambda: object(),
            CharacterDependencies.require_character_moderator: deny_access,
        }
    )
    with TestClient(app) as client:
        result = client.patch(
            "/characters/status",
            json={
                "character_id": str(uuid4()),
                "status": "approved",
            },
        )
    assert result.status_code == 403
    change.assert_not_awaited()
