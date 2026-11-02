"""A published studio document cannot change the live product profile as a draft."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.product import Product, ProductStudioDraft
from app.modules.content.product import types as ProductTypes
from app.modules.content.product.service import tags as TagsService
from app.modules.content.product.service.command import studio


@pytest.mark.asyncio
@pytest.mark.parametrize("visibility", ["private", "public", "unlisted"])
async def test_edit_after_first_publication_does_not_change_product_visibility(
    monkeypatch: pytest.MonkeyPatch,
    visibility: str,
) -> None:
    owner_id, product_id = uuid4(), uuid4()
    now = datetime.now(UTC)
    product = Product(
        id=product_id,
        owner_id=owner_id,
        title="Published work",
        description=None,
        opening_message="Hello",
        status="approved",
        visibility=visibility,
        latest_snapshot_id=uuid4(),
        replacement_policy={},
        created_at=now,
        updated_at=now,
    )
    draft = ProductStudioDraft(
        product_id=product_id,
        revision=1,
        content_digest="previous",
        document={},
        publication_digest="previous",
        publication_release={"version": 1},
        updated_at=now,
    )
    update = AsyncMock()
    monkeypatch.setattr(studio, "lock_key", AsyncMock())
    monkeypatch.setattr(
        studio.Repository, "get_product_for_update", AsyncMock(return_value=product)
    )
    monkeypatch.setattr(
        studio.Repository, "get_studio_draft", AsyncMock(return_value=draft)
    )
    monkeypatch.setattr(studio.Repository, "update_product", update)

    async def save(
        session: AsyncSession,
        product_id: UUID,
        revision: int,
        digest: str,
        document: ProductTypes.ProductJsonObject,
        existing: ProductStudioDraft | None,
    ) -> ProductStudioDraft:
        assert session.in_transaction() and existing is draft
        draft.revision, draft.content_digest, draft.document = (
            revision,
            digest,
            document,
        )
        return draft

    write = AsyncMock(side_effect=save)
    tags = AsyncMock()
    monkeypatch.setattr(studio.Repository, "save_studio_draft", write)
    monkeypatch.setattr(TagsService, "replace_public_tags", tags)

    document: ProductTypes.ProductJsonObject = {
        "version": 2,
        "work": {
            "title": "Changed draft title",
            "introduction": "Changed draft introduction",
            "visibility": "전체 공개",
            "defaultSceneId": "scene",
            "tags": ["new draft tag"],
        },
        "scenes": [{"id": "scene", "opening": "Changed draft opening"}],
    }
    command = ProductTypes.SaveStudioDraftCommand(product_id, owner_id, 1, document)
    snapshot_id = product.latest_snapshot_id
    async with AsyncSession() as session:
        saved = await studio.save_studio_draft(session, command)
    assert saved.revision == 2 and saved.document == document
    assert saved.publication_digest == "previous"
    assert saved.publication_release == {"version": 1}
    assert product.visibility == visibility and product.status == "approved"
    assert product.title == "Published work" and product.description is None
    assert (
        product.opening_message == "Hello" and product.latest_snapshot_id == snapshot_id
    )
    update.assert_not_awaited()
    tags.assert_not_awaited()
    write.assert_awaited_once()
