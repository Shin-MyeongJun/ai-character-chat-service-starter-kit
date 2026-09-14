"""Real PostgreSQL transactions with local and mock S3 storage."""

import asyncio
import io
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio
from app.db.models.character import CharacterImage
from app.db.models.character_media import CharacterMedia
from app.db.models.product import Product
from app.db.models.snapshot.character import CharacterSnapshotImage
from app.db.models.snapshot.product import ProductSnapshot
from app.db.transaction import use_case_transaction
from app.modules.asset_storage import types as StorageTypes
from app.modules.asset_storage.service import AssetStorageService
from app.modules.content.character import repository as Repository
from app.modules.content.character import types as Types
from app.modules.content.character.service import command as Commands
from app.modules.content.character.service.media import CharacterMediaService
from app.modules.content.product import types as ProductTypes
from app.modules.content.product.service.command.releases import publish_product
from app.modules.content.product.service.views.media import ProductMediaService
from sqlalchemy import event, func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker
from test_asset_storage import FakeS3Client, _local_adapter, _s3_adapter
from test_product_integration import ready_product, seed

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture(params=["test_local", "s3"])
async def media(db, tmp_path, request):
    adapter = (
        _local_adapter(tmp_path)
        if request.param == "test_local"
        else _s3_adapter(FakeS3Client())
    )
    async with AssetStorageService(adapter) as storage:
        yield CharacterMediaService(
            async_sessionmaker(db.bind, expire_on_commit=False),
            storage,
            storage_kind=request.param,
            storage_id="local-a" if request.param == "test_local" else "seoul-assets",
        )


def upload(
    owner, character, *, request_id=None, payload=b"image-one", content_type="image/png"
):
    return Types.UploadCharacterMediaCommand(
        character.id,
        owner.id,
        request_id or uuid4(),
        io.BytesIO(payload),
        content_type,
        "portrait.png",
        "portrait",
    )


def attachment(info, tag="normal"):
    return Types.CreateCharacterImageCommand(
        info.character_id, info.owner_id, tag, info.content_url
    )


async def age_media(db, media_id):
    async with use_case_transaction(db):
        await db.execute(
            update(CharacterMedia)
            .where(CharacterMedia.id == media_id)
            .values(updated_at=datetime.now(UTC) - timedelta(days=3))
        )


def cleanup(media_id):
    return Types.CleanupCharacterMediaCommand(
        media_id, datetime.now(UTC) - timedelta(days=1)
    )


async def stored_state(db, media_id):
    async with use_case_transaction(db):
        return await db.scalar(
            select(CharacterMedia.state).where(CharacterMedia.id == media_id)
        )


async def test_upload_attach_retry_and_validation(db, media):
    owner, c, _ = await seed(db)
    value = upload(owner, c)
    info = await media.upload_character_media(value)
    assert info.state == "ready"
    assert info.storage_kind == media.storage_kind
    assert info.size_bytes == len(b"image-one")
    assert await media.upload_character_media(value) == info
    with pytest.raises(ValueError, match="different media"):
        await media.upload_character_media(
            replace(value, content=io.BytesIO(b"changed"))
        )
    image = await Commands.add_character_image(db, attachment(info))
    assert (await Commands.add_character_image(db, attachment(info))).id == image.id
    with pytest.raises(ValueError, match="different metadata"):
        await Commands.add_character_image(db, attachment(info, "changed"))
    async with await media.read_character_media(
        Types.ReadCharacterMediaCommand(info.id, owner.id)
    ) as opened:
        assert await opened.read() == b"image-one"
    await Commands.delete_character_image(
        db, Types.DeleteCharacterImageCommand(info.character_id, image.id, owner.id)
    )
    with pytest.raises(ValueError, match="deleted"):
        await Commands.add_character_image(db, attachment(info))
    # Replaying an upload never silently recreates an attachment.
    assert (await media.upload_character_media(value)).id == info.id


async def test_concurrent_upload_and_attach_are_idempotent(db, media):
    owner, c, _ = await seed(db)
    request_id = uuid4()
    first, second = await asyncio.gather(
        *[
            media.upload_character_media(upload(owner, c, request_id=request_id))
            for _ in range(2)
        ]
    )
    assert first.id == second.id

    async def attach():
        async with media.sessions() as session:
            return await Commands.add_character_image(session, attachment(first))

    a, b = await asyncio.gather(attach(), attach())
    assert a.id == b.id
    async with use_case_transaction(db):
        assert await db.scalar(select(func.count()).select_from(CharacterMedia)) == 1
        assert await db.scalar(select(func.count()).select_from(CharacterImage)) == 1


async def test_authorization_precedes_storage_and_binding(db, media, monkeypatch):
    owner, c, _ = await seed(db)
    other, other_c, _ = await seed(db)
    info = await media.upload_character_media(upload(owner, c))
    store = AsyncMock(wraps=media.storage.store_asset)
    read = AsyncMock(wraps=media.storage.read_asset)
    monkeypatch.setattr(media.storage, "store_asset", store)
    monkeypatch.setattr(media.storage, "read_asset", read)
    with pytest.raises(LookupError):
        await media.upload_character_media(upload(other, c))
    with pytest.raises(LookupError):
        await media.read_character_media(
            Types.ReadCharacterMediaCommand(info.id, other.id)
        )
    with pytest.raises(LookupError):
        await Commands.add_character_image(
            db, replace(attachment(info), character_id=other_c.id, owner_id=other.id)
        )
    with pytest.raises(LookupError):
        await media.read_snapshot_media(
            Types.ReadSnapshotMediaCommand(info.id, (uuid4(),))
        )
    store.assert_not_awaited()
    read.assert_not_awaited()


async def test_reservation_failure_performs_no_file_io(db, media, monkeypatch):
    owner, c, _ = await seed(db)
    store = AsyncMock()
    monkeypatch.setattr(media.storage, "store_asset", store)
    monkeypatch.setattr(
        Repository,
        "create_media",
        AsyncMock(side_effect=RuntimeError("DB reservation")),
    )
    with pytest.raises(RuntimeError, match="DB reservation"):
        await media.upload_character_media(upload(owner, c))
    store.assert_not_awaited()


async def test_storage_failure_keeps_pending_intent_and_retry(db, media, monkeypatch):
    owner, c, _ = await seed(db)
    value = upload(owner, c)
    original = media.storage.store_asset
    monkeypatch.setattr(
        media.storage,
        "store_asset",
        AsyncMock(side_effect=RuntimeError("file failure")),
    )
    with pytest.raises(RuntimeError, match="file failure"):
        await media.upload_character_media(value)
    async with use_case_transaction(db):
        saved = await db.scalar(select(CharacterMedia))
        assert saved.state == "pending"
        media_id = saved.id
    monkeypatch.setattr(media.storage, "store_asset", original)
    assert (await media.upload_character_media(value)).id == media_id


async def test_file_success_then_actual_db_commit_failure_is_recoverable(
    db, media, monkeypatch
):
    owner, c, _ = await seed(db)
    value = upload(owner, c)
    original = Repository.set_media_state

    async def fail_commit(session, media_id, state):
        await original(session, media_id, state)

        def fail(_):
            raise RuntimeError("commit failed")

        event.listen(session.sync_session, "before_commit", fail, once=True)

    monkeypatch.setattr(Repository, "set_media_state", fail_commit)
    with pytest.raises(RuntimeError, match="commit failed"):
        await media.upload_character_media(value)
    async with use_case_transaction(db):
        saved = await db.scalar(select(CharacterMedia))
        assert saved.state == "pending"
        media_id, key = saved.id, saved.object_key
    async with await media.storage.read_asset(
        StorageTypes.ReadAssetCommand(key)
    ) as opened:
        assert await opened.read() == b"image-one"
    monkeypatch.setattr(Repository, "set_media_state", original)
    assert (await media.upload_character_media(value)).id == media_id


async def test_attach_failure_rolls_back_binding_and_preserves_uploaded_object(
    db, media, monkeypatch
):
    owner, c, _ = await seed(db)
    info = await media.upload_character_media(upload(owner, c))
    original = Repository.create_media_attachment
    monkeypatch.setattr(
        Repository,
        "create_media_attachment",
        AsyncMock(side_effect=RuntimeError("attachment DB")),
    )
    with pytest.raises(RuntimeError, match="attachment DB"):
        await Commands.add_character_image(db, attachment(info))
    monkeypatch.setattr(Repository, "create_media_attachment", original)
    await Commands.add_character_image(db, attachment(info))
    assert await stored_state(db, info.id) == "ready"


async def test_cleanup_failure_and_db_finalize_failure_resume_without_success_masking(
    db, media, monkeypatch
):
    owner, c, _ = await seed(db)
    value = upload(owner, c)
    info = await media.upload_character_media(value)
    await age_media(db, info.id)
    original_delete = media.storage.delete_asset
    monkeypatch.setattr(
        media.storage,
        "delete_asset",
        AsyncMock(side_effect=RuntimeError("delete failed")),
    )
    with pytest.raises(RuntimeError, match="delete failed"):
        await media.cleanup_character_media(cleanup(info.id))
    assert await stored_state(db, info.id) == "deleting"
    with pytest.raises(ValueError, match="retired"):
        await media.upload_character_media(value)
    with pytest.raises(ValueError, match="ready"):
        await Commands.add_character_image(db, attachment(info))
    monkeypatch.setattr(media.storage, "delete_asset", original_delete)
    original_state = Repository.set_media_state

    async def fail_finalize(session, media_id, state):
        if state == "deleted":
            raise RuntimeError("finalize failed")
        await original_state(session, media_id, state)

    monkeypatch.setattr(Repository, "set_media_state", fail_finalize)
    with pytest.raises(RuntimeError, match="finalize failed"):
        await media.cleanup_character_media(cleanup(info.id))
    assert await stored_state(db, info.id) == "deleting"
    with pytest.raises(StorageTypes.AssetNotFoundError):
        await media.storage.get_asset_metadata(
            StorageTypes.GetAssetMetadataCommand(info.object_key)
        )
    monkeypatch.setattr(Repository, "set_media_state", original_state)
    assert (await media.cleanup_character_media(cleanup(info.id))).deleted
    assert not (await media.cleanup_character_media(cleanup(info.id))).deleted


async def test_cleanup_retention_and_draft_references(db, media):
    owner, c, _ = await seed(db)
    info = await media.upload_character_media(upload(owner, c))
    assert (await media.cleanup_character_media(cleanup(info.id))).reason == "retention"
    image = await Commands.add_character_image(db, attachment(info))
    await age_media(db, info.id)
    assert (
        await media.cleanup_character_media(cleanup(info.id))
    ).reason == "referenced"
    await Commands.delete_character_image(
        db, Types.DeleteCharacterImageCommand(c.id, image.id, owner.id)
    )
    assert (await media.cleanup_character_media(cleanup(info.id))).deleted


async def test_versions_keep_immutable_media_after_replacement_and_character_deletion(
    db, media
):
    owner, c, _, product, _, _ = await ready_product(db)
    info = await media.upload_character_media(upload(owner, c))
    image = await Commands.add_character_image(db, attachment(info))
    audio = await media.upload_character_media(
        upload(owner, c, payload=b"audio", content_type="audio/ogg")
    )
    asset = await Commands.add_character_asset(
        db,
        Types.CreateCharacterAssetCommand(
            c.id, owner.id, "audio", "voice", audio.content_url
        ),
    )

    async def publish():
        return await publish_product(
            db,
            ProductTypes.PublishCommand(
                product_id=product.id,
                owner_id=owner.id,
                value=ProductTypes.ReleaseNoteCommand("Release", "Media"),
            ),
        )

    first = await publish()
    await Commands.set_default_character_image(
        db, Types.SetDefaultCharacterImageCommand(c.id, image.id, owner.id)
    )
    async with use_case_transaction(db):
        saved = await db.scalar(select(CharacterSnapshotImage))
        assert saved.media_id == info.id and not saved.is_default
    await Commands.delete_character_image(
        db, Types.DeleteCharacterImageCommand(c.id, image.id, owner.id)
    )
    await Commands.delete_character_asset(
        db, Types.DeleteCharacterAssetCommand(c.id, asset.id, owner.id)
    )
    replacement = await media.upload_character_media(
        upload(owner, c, payload=b"image-two")
    )
    await Commands.add_character_image(db, attachment(replacement))
    second = await publish()
    assert info.object_key != replacement.object_key
    product_media = ProductMediaService(media.sessions, media)
    async with await product_media.read_product_media(
        ProductTypes.ReadProductMediaCommand(
            product.id, first.snapshot_id, info.id, owner.id
        )
    ) as opened:
        assert await opened.read() == b"image-one"
    with pytest.raises(LookupError):
        await product_media.read_product_media(
            ProductTypes.ReadProductMediaCommand(
                product.id, second.snapshot_id, info.id, owner.id
            )
        )
    with pytest.raises(LookupError):
        await product_media.read_product_media(
            ProductTypes.ReadProductMediaCommand(
                product.id, first.snapshot_id, info.id, uuid4()
            )
        )
    async with use_case_transaction(db):
        await db.execute(
            update(Product)
            .where(Product.id == product.id)
            .values(status="approved", visibility="public")
        )
    async with await product_media.read_product_media(
        ProductTypes.ReadProductMediaCommand(
            product.id, first.snapshot_id, info.id, uuid4()
        )
    ) as opened:
        assert await opened.read() == b"image-one"
    await Commands.delete_character(db, Types.DeleteCharacterCommand(c.id, owner.id))
    for saved in (info, audio, replacement):
        await age_media(db, saved.id)
        assert (
            await media.cleanup_character_media(cleanup(saved.id))
        ).reason == "referenced"
    async with await product_media.read_product_media(
        ProductTypes.ReadProductMediaCommand(
            product.id, first.snapshot_id, audio.id, owner.id
        )
    ) as opened:
        assert await opened.read() == b"audio"
    with pytest.raises(LookupError):
        await media.read_character_media(
            Types.ReadCharacterMediaCommand(info.id, owner.id)
        )
    other_product_id = uuid4()
    async with use_case_transaction(db):
        db.add(Product(id=other_product_id, owner_id=owner.id, title="Other"))
    with pytest.raises(LookupError, match="Version"):
        await product_media.read_product_media(
            ProductTypes.ReadProductMediaCommand(
                other_product_id, first.snapshot_id, info.id, owner.id
            )
        )
    async with use_case_transaction(db):
        await db.execute(
            update(ProductSnapshot)
            .where(ProductSnapshot.id == first.snapshot_id)
            .values(expires_at=datetime.now(UTC) - timedelta(days=1))
        )
    with pytest.raises(ValueError, match="expired"):
        await product_media.read_product_media(
            ProductTypes.ReadProductMediaCommand(
                product.id, first.snapshot_id, info.id, owner.id
            )
        )
    assert (
        await media.cleanup_character_media(cleanup(info.id))
    ).reason == "referenced"


async def test_legacy_references_and_unknown_storage_do_not_touch_other_files(
    db, media, monkeypatch
):
    owner, c, _ = await seed(db)
    image = await Commands.add_character_image(
        db,
        Types.CreateCharacterImageCommand(
            c.id, owner.id, "legacy", "https://legacy.invalid/keep.png"
        ),
    )
    await Commands.freeze_character(db, Types.FreezeCharacterCommand(c.id, owner.id))
    await Commands.delete_character_image(
        db, Types.DeleteCharacterImageCommand(c.id, image.id, owner.id)
    )
    async with use_case_transaction(db):
        saved = await db.scalar(select(CharacterSnapshotImage))
        assert (
            saved.image_url == "https://legacy.invalid/keep.png"
            and saved.media_id is None
        )
    info = await media.upload_character_media(upload(owner, c))
    read = AsyncMock()
    monkeypatch.setattr(media.storage, "read_asset", read)
    media.storages = {}
    with pytest.raises(StorageTypes.AssetStorageConfigurationError):
        await media.read_character_media(
            Types.ReadCharacterMediaCommand(info.id, owner.id)
        )
    read.assert_not_awaited()


async def test_cancelled_upload_settles_before_retry_or_cleanup(db, media, monkeypatch):
    owner, c, _ = await seed(db)
    value = upload(owner, c)
    started, release = asyncio.Event(), asyncio.Event()
    original = media.storage.store_asset

    async def delayed(command):
        started.set()
        await release.wait()
        return await original(command)

    monkeypatch.setattr(media.storage, "store_asset", delayed)
    task = asyncio.create_task(media.upload_character_media(value))
    await started.wait()
    task.cancel()
    await asyncio.sleep(0)
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    monkeypatch.setattr(media.storage, "store_asset", original)
    info = await media.upload_character_media(value)
    assert info.state == "ready"


async def test_concurrent_cleanup_and_attachment_never_delete_referenced_media(
    db, media
):
    owner, c, _ = await seed(db)
    info = await media.upload_character_media(upload(owner, c))
    await age_media(db, info.id)

    async def attach():
        async with media.sessions() as session:
            return await Commands.add_character_image(session, attachment(info))

    attached, collected = await asyncio.gather(
        attach(),
        media.cleanup_character_media(cleanup(info.id)),
        return_exceptions=True,
    )
    assert not isinstance(collected, Exception)
    if isinstance(attached, ValueError):
        assert collected.deleted
    else:
        assert isinstance(attached, Types.CharacterImageInfo)
        assert not collected.deleted
        async with await media.read_character_media(
            Types.ReadCharacterMediaCommand(info.id, owner.id)
        ) as opened:
            assert await opened.read() == b"image-one"


async def test_failed_retry_refreshes_durable_cleanup_grace(db, media, monkeypatch):
    owner, c, _ = await seed(db)
    value = upload(owner, c)
    monkeypatch.setattr(
        media.storage,
        "store_asset",
        AsyncMock(side_effect=RuntimeError("storage unavailable")),
    )
    with pytest.raises(RuntimeError, match="unavailable"):
        await media.upload_character_media(value)
    async with use_case_transaction(db):
        media_id = await db.scalar(select(CharacterMedia.id))
    await age_media(db, media_id)
    with pytest.raises(RuntimeError, match="unavailable"):
        await media.upload_character_media(value)
    assert (
        await media.cleanup_character_media(cleanup(media_id))
    ).reason == "retention"
