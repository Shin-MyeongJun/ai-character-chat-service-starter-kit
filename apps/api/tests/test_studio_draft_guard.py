"""A published studio document cannot change the live product profile as a draft."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.modules.content.product import types as ProductTypes
from app.modules.content.product.service.command import studio


@pytest.mark.asyncio
async def test_edit_after_first_publication_does_not_change_product_visibility(monkeypatch):
    @asynccontextmanager
    async def transaction(_session):
        yield

    owner_id, product_id = uuid4(), uuid4()
    product = SimpleNamespace(id=product_id, owner_id=owner_id)
    draft = SimpleNamespace(revision=1, content_digest="previous", publication_release={"version": 1})
    update = AsyncMock()
    monkeypatch.setattr(studio, "use_case_transaction", transaction)
    monkeypatch.setattr(studio, "lock_key", AsyncMock())
    monkeypatch.setattr(studio.Repository, "get_product_for_update", AsyncMock(return_value=product))
    monkeypatch.setattr(studio.PersistenceMapper, "product_entity_to_state_info", lambda row: row)
    monkeypatch.setattr(studio.Repository, "get_studio_draft", AsyncMock(return_value=draft))
    monkeypatch.setattr(studio.Repository, "update_product", update)
    monkeypatch.setattr(studio.Repository, "save_studio_draft", AsyncMock())

    document = {
        "version": 2,
        "work": {"title": "Published work", "introduction": "", "visibility": "전체 공개", "defaultSceneId": "scene"},
        "scenes": [{"id": "scene", "opening": "Hello"}],
    }
    command = ProductTypes.SaveStudioDraftCommand(product_id, owner_id, 1, document)
    with pytest.raises(ProductTypes.StudioDraftConflictError, match="follow-up releases"):
        await studio.save_studio_draft(object(), command)
    update.assert_not_awaited()
    studio.Repository.save_studio_draft.assert_not_awaited()
