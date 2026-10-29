"""Studio revision/digest/receipt contracts with valid entities and offline SQL."""

import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import JSON, Column, MetaData, Table, Uuid, text, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from test_product_core_contracts import database as core_database_fixture

from app.db.models.product import Product, ProductStudioDraft
from app.modules.content.product import types
from app.modules.content.product.repository import studio as Repository
from app.modules.content.product.service import tags as TagsService
from app.modules.content.product.service.command import studio
from app.modules.content.product.service.query import studio as StudioQuery

core_database = core_database_fixture


def document(title="Draft", tags=None):
    work = {
        "title": title,
        "introduction": "",
        "visibility": "전체 공개",
        "defaultSceneId": "start",
    }
    if tags is not None:
        work["tags"] = tags
    return {"version": 2, "work": work, "scenes": [{"id": "start", "opening": "Hello"}]}


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


@pytest_asyncio.fixture
async def saved(monkeypatch):
    now = datetime.now(UTC)
    product = Product(
        id=uuid4(),
        owner_id=uuid4(),
        title="Draft",
        description=None,
        opening_message="Hello",
        visibility="private",
        status="draft",
        replacement_policy={},
        created_at=now,
        updated_at=now,
    )
    draft = ProductStudioDraft(
        product_id=product.id,
        revision=3,
        document=document(),
        content_digest=digest(document()),
        publication_digest=None,
        publication_release=None,
        updated_at=now,
    )
    get_product = AsyncMock(return_value=product)
    get_draft = AsyncMock(return_value=draft)
    create = AsyncMock(return_value=product)
    update_product = AsyncMock(return_value=product)

    async def save(_session, product_id, revision, content_digest, value, existing):
        row = (
            existing
            if existing is not None
            else ProductStudioDraft(product_id=product_id)
        )
        row.revision, row.content_digest, row.document = revision, content_digest, value
        row.updated_at = now
        return row

    async def mark(_session, row, publication_digest, receipt):
        row.publication_digest, row.publication_release = publication_digest, receipt

    write, mark_write, tags, lock = (
        AsyncMock(side_effect=save),
        AsyncMock(side_effect=mark),
        AsyncMock(),
        AsyncMock(),
    )
    monkeypatch.setattr(studio.Repository, "get_product_for_update", get_product)
    monkeypatch.setattr(studio.Repository, "get_studio_draft", get_draft)
    monkeypatch.setattr(studio.Repository, "create_product", create)
    monkeypatch.setattr(studio.Repository, "update_product", update_product)
    monkeypatch.setattr(studio.Repository, "save_studio_draft", write)
    monkeypatch.setattr(studio.Repository, "mark_studio_publication", mark_write)
    monkeypatch.setattr(TagsService, "replace_public_tags", tags)
    monkeypatch.setattr(studio, "lock_key", lock)
    async with AsyncSession() as session:
        yield SimpleNamespace(
            session=session,
            product=product,
            draft=draft,
            get_product=get_product,
            get_draft=get_draft,
            create=create,
            update=update_product,
            write=write,
            mark=mark_write,
            tags=tags,
            lock=lock,
        )


@pytest.mark.asyncio
async def test_same_document_retry_precedes_revision_conflict_and_does_not_write(saved):
    result = await studio.save_studio_draft(
        saved.session,
        types.SaveStudioDraftCommand(
            saved.product.id, saved.product.owner_id, 1, document()
        ),
    )
    assert result.revision == 3 and result.content_digest == saved.draft.content_digest
    saved.write.assert_not_awaited()
    saved.update.assert_not_awaited()
    saved.tags.assert_not_awaited()
    saved.lock.assert_awaited_once_with(
        saved.session, "product-studio-draft", str(saved.product.id)
    )
    assert not saved.session.in_transaction()


@pytest.mark.asyncio
@pytest.mark.parametrize("create_new", [True, False])
async def test_save_keeps_profile_projection_revision_and_document_digest(
    saved, create_new
):
    value = document("Changed", ["Fantasy"])
    if create_new:
        saved.get_product.return_value = None
        saved.get_draft.return_value = None
    result = await studio.save_studio_draft(
        saved.session,
        types.SaveStudioDraftCommand(
            saved.product.id, saved.product.owner_id, None if create_new else 3, value
        ),
    )
    assert result.revision == (1 if create_new else 4)
    assert result.content_digest == digest(value) and result.document == value
    profile = types.ProductProfileCommand("Changed", None, "Hello", "public")
    if create_new:
        saved.create.assert_awaited_once_with(
            saved.session, saved.product.owner_id, profile, product_id=saved.product.id
        )
        saved.update.assert_not_awaited()
    else:
        saved.update.assert_awaited_once_with(
            saved.session, saved.product.id, saved.product.owner_id, profile
        )
    saved.tags.assert_awaited_once_with(
        saved.session,
        types.PublicTagsCommand(
            target_id=saved.product.id,
            user_id=saved.product.owner_id,
            names=("Fantasy",),
        ),
    )
    assert not saved.session.in_transaction()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["stale", "foreign", "removed", "tag_shape"])
async def test_invalid_revision_owner_or_tag_shape_prevents_draft_write(saved, failure):
    owner_id = saved.product.owner_id
    expected = 2 if failure == "stale" else 3
    value = document("Changed")
    error = types.StudioDraftConflictError
    if failure == "foreign":
        owner_id, error = uuid4(), LookupError
    elif failure == "removed":
        saved.get_product.return_value = None
    elif failure == "tag_shape":
        value["work"]["tags"] = "invalid sequence"
        error = ValueError
    with pytest.raises(error):
        await studio.save_studio_draft(
            saved.session,
            types.SaveStudioDraftCommand(saved.product.id, owner_id, expected, value),
        )
    saved.write.assert_not_awaited()
    saved.tags.assert_not_awaited()
    assert not saved.session.in_transaction()


@pytest.mark.asyncio
async def test_receipt_and_component_mapping_keep_revision_and_content_digest(saved):
    release = types.ReleaseInfo(uuid4(), 1, "Summary", "Body", "initial", "choice")
    mapping = {"characters": {"hero": str(uuid4())}}
    result = await studio.mark_studio_publication(
        saved.session,
        types.MarkStudioPublicationCommand(
            saved.product.id,
            saved.product.owner_id,
            saved.draft.content_digest,
            release,
            mapping,
        ),
    )
    assert result == release
    expected_receipt = {
        "snapshot_id": str(release.snapshot_id),
        "version": 1,
        "summary": "Summary",
        "body": "Body",
        "change_kind": "initial",
        "update_policy": "choice",
        "_studio": mapping,
    }
    assert saved.draft.publication_release == expected_receipt
    original_digest = saved.draft.content_digest
    next_mapping = {"characters": {"hero": str(uuid4())}, "receipts": {}}
    info = await studio.set_studio_components(
        saved.session,
        types.SetStudioComponentsCommand(
            saved.product.id, saved.product.owner_id, 3, next_mapping
        ),
    )
    assert info.revision == 3 and info.content_digest == original_digest
    assert info.publication_digest == original_digest
    assert info.publication_release == {**expected_receipt, "_studio": next_mapping}
    saved.write.assert_not_awaited()
    assert not saved.session.in_transaction()


@pytest.mark.asyncio
@pytest.mark.parametrize("publication_read", [True, False])
async def test_studio_read_checks_owner_and_uses_matching_lock(
    saved, monkeypatch, publication_read
):
    owned = AsyncMock()
    monkeypatch.setattr(StudioQuery.QueryService, "get_owned_product", owned)
    function = (
        StudioQuery.get_studio_draft_for_publication
        if publication_read
        else StudioQuery.get_studio_draft
    )
    command = types.GetStudioDraftCommand(saved.product.id, saved.product.owner_id)
    info = await function(saved.session, command)
    owned.assert_awaited_once_with(
        saved.session,
        types.OwnedProductCommand(
            product_id=saved.product.id,
            owner_id=saved.product.owner_id,
            lock=publication_read,
        ),
    )
    assert info.document == saved.draft.document
    if publication_read:
        saved.get_draft.assert_awaited_once_with(
            saved.session, saved.product.id, lock=True
        )
    else:
        saved.get_draft.assert_awaited_once_with(saved.session, saved.product.id)
    saved.get_draft.return_value = None
    with pytest.raises(LookupError, match="Studio draft not found"):
        await function(saved.session, command)


@pytest.mark.asyncio
async def test_studio_repository_create_update_refresh_and_receipt(core_database):
    sync_session, session = core_database
    metadata = MetaData()
    columns = []
    for column in ProductStudioDraft.__table__.columns:
        column_type = JSON() if isinstance(column.type, JSONB) else column.type
        if isinstance(column_type, Uuid):
            column_type = Uuid(native_uuid=False)
        columns.append(
            Column(
                column.name,
                column_type,
                primary_key=column.primary_key,
                server_default=text("CURRENT_TIMESTAMP")
                if column.name in ("created_at", "updated_at")
                else None,
            )
        )
    Table(ProductStudioDraft.__tablename__, metadata, *columns)
    metadata.create_all(sync_session.get_bind())
    product_id = uuid4()
    assert await Repository.get_studio_draft(session, product_id) is None
    row = await Repository.save_studio_draft(
        session, product_id, 1, "first", document(), None
    )
    assert await Repository.get_studio_draft(session, product_id, lock=True) is row
    updated = document("Changed")
    assert (
        await Repository.save_studio_draft(
            session, product_id, 2, "second", updated, row
        )
        is row
    )
    assert (
        row.revision == 2 and row.content_digest == "second" and row.document == updated
    )
    receipt = {"_studio": {"characters": {"hero": "server-copy"}}}
    await Repository.mark_studio_publication(session, row, None, deepcopy(receipt))
    assert row.publication_digest is None and row.publication_release == receipt
    sync_session.execute(
        update(ProductStudioDraft)
        .values(revision=7)
        .execution_options(synchronize_session=False)
    )
    assert row.revision == 2
    assert (
        await Repository.get_studio_draft(session, product_id, lock=True)
    ).revision == 7
