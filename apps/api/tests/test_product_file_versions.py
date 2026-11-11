"""U19 a2 file identity, privacy, durable storage and retention in PostgreSQL."""

import asyncio
import io
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from test_character_media import (  # noqa: F401 - parametrized storage fixture
    media,
    upload,
)
from test_product_integration import seed

from app.db.models.character_media import CharacterMedia
from app.db.models.product_file_version import ProductFileVersion
from app.db.transaction import use_case_transaction
from app.http import dependencies
from app.http.media import router
from app.modules.asset_storage import types as StorageTypes
from app.modules.content.character import types as CharacterTypes
from app.modules.content.character.service.workflow.media import CharacterMediaWorkflow
from app.modules.content.product import types as Types
from app.modules.content.product.service.command import create_product
from app.modules.content.product.service.command.file_versions import (
    release_product_file_version,
    retain_product_file_version,
)
from app.modules.content.product.service.workflow.file_versions import (
    ProductFileVersionWorkflow,
)

pytestmark = pytest.mark.asyncio


def workflow(character_media: CharacterMediaWorkflow) -> ProductFileVersionWorkflow:
    return ProductFileVersionWorkflow(
        character_media.sessions,
        character_media.storage,
        character_media,
        storage_kind=character_media.storage_kind,
        storage_id=character_media.storage_id,
    )


async def product_for(db: AsyncSession, owner_id: UUID) -> UUID:
    return (
        await create_product(
            db,
            Types.CreateProductCommand(
                owner_id=owner_id, value=Types.ProductProfileCommand("Private images")
            ),
        )
    ).id


def image_upload(
    product_id: UUID, owner_id: UUID, payload: bytes = b"image-one"
) -> Types.UploadProductFileVersionCommand:
    return Types.UploadProductFileVersionCommand(
        product_id=product_id,
        owner_id=owner_id,
        request_id=uuid4(),
        content=io.BytesIO(payload),
        content_type="image/png",
        original_filename="one.png",
    )


async def age_reference_clock(
    db: AsyncSession, file_version_id: UUID, elapsed: timedelta
) -> None:
    async with use_case_transaction(db):
        await db.execute(
            update(ProductFileVersion)
            .where(ProductFileVersion.id == file_version_id)
            .values(unreferenced_since=datetime.now(UTC) - elapsed)
        )


async def test_upload_identity_conflicts_and_product_scope(
    db: AsyncSession,
    media: CharacterMediaWorkflow,  # noqa: F811
) -> None:
    owner, _, _ = await seed(db)
    product_id = await product_for(db, owner.id)
    other_product_id = await product_for(db, owner.id)
    service = workflow(media)
    command = image_upload(product_id, owner.id)
    first, replay = await asyncio.gather(
        service.upload_product_file_version(command),
        service.upload_product_file_version(
            replace(command, content=io.BytesIO(b"image-one"))
        ),
    )
    assert first == replay
    assert first.state == Types.ProductFileVersionState.READY
    for changed in (
        replace(command, content=io.BytesIO(b"image-two")),
        replace(command, original_filename="renamed.png"),
        replace(command, content_type="image/webp"),
    ):
        with pytest.raises(Types.ProductFileVersionConflictError):
            await service.upload_product_file_version(changed)

    replacement = await service.upload_product_file_version(
        image_upload(product_id, owner.id, b"image-two")
    )
    other = await service.upload_product_file_version(
        replace(command, product_id=other_product_id)
    )
    assert (
        len({first.file_version_id, replacement.file_version_id, other.file_version_id})
        == 3
    )
    preview = Types.ReadOwnedProductFileVersionCommand(
        product_id=product_id,
        owner_id=owner.id,
        file_version_id=first.file_version_id,
    )
    async with await service.read_owned_product_file_version(preview) as opened:
        assert await opened.read() == b"image-one"
    with pytest.raises(LookupError):
        await service.read_owned_product_file_version(
            replace(preview, product_id=other_product_id)
        )
    with pytest.raises(LookupError):
        await service.read_owned_product_file_version(
            replace(preview, owner_id=uuid4())
        )
    with pytest.raises(LookupError):
        await service.upload_product_file_version(replace(command, owner_id=uuid4()))


async def test_explicit_import_copies_owned_ready_source(
    db: AsyncSession,
    media: CharacterMediaWorkflow,  # noqa: F811
) -> None:
    owner, character, _ = await seed(db)
    other, other_character, _ = await seed(db)
    product_id = await product_for(db, owner.id)
    service = workflow(media)
    source = await media.upload_character_media(upload(owner, character))
    foreign = await media.upload_character_media(upload(other, other_character))
    command = Types.ImportProductFileVersionCommand(
        product_id=product_id, owner_id=owner.id, request_id=uuid4(), media_id=source.id
    )
    with pytest.raises(LookupError):
        await service.import_product_file_version(replace(command, media_id=foreign.id))
    async with use_case_transaction(db):
        await db.execute(
            update(CharacterMedia)
            .where(CharacterMedia.id == source.id)
            .values(state="pending")
        )
    with pytest.raises(LookupError):
        await service.import_product_file_version(command)
    # The existing upload resumes its reservation and makes the source ready.
    await media.upload_character_media(
        upload(owner, character, request_id=source.request_id)
    )
    copied = await service.import_product_file_version(command)
    assert copied.file_version_id != source.id
    assert copied.original_filename == source.original_filename
    with pytest.raises(Types.ProductFileVersionConflictError):
        await service.import_product_file_version(replace(command, media_id=foreign.id))
    with pytest.raises(Types.ProductFileVersionConflictError):
        await service.upload_product_file_version(
            replace(
                image_upload(product_id, owner.id),
                request_id=command.request_id,
                original_filename=source.original_filename,
            )
        )
    preview = Types.ReadOwnedProductFileVersionCommand(
        product_id=product_id,
        owner_id=owner.id,
        file_version_id=copied.file_version_id,
    )
    await media.storage.delete_asset(StorageTypes.DeleteAssetCommand(source.object_key))
    async with await service.read_owned_product_file_version(preview) as opened:
        assert opened.metadata.object_key != source.object_key
        assert await opened.read() == b"image-one"
    assert await service.import_product_file_version(command) == copied
    with pytest.raises(LookupError):
        await service.read_owned_product_file_version(
            replace(preview, file_version_id=source.id)
        )
    with pytest.raises(LookupError):
        await media.read_character_media(
            CharacterTypes.ReadCharacterMediaCommand(copied.file_version_id, owner.id)
        )


async def test_failed_upload_keeps_reservation_and_retries_same_id(
    db: AsyncSession,
    media: CharacterMediaWorkflow,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner, _, _ = await seed(db)
    product_id = await product_for(db, owner.id)
    service = workflow(media)
    command = image_upload(product_id, owner.id)
    store_asset = media.storage.store_asset

    async def fail_store(
        command: StorageTypes.StoreAssetCommand,
    ) -> StorageTypes.StoredAssetInfo:
        raise OSError("storage interrupted")

    monkeypatch.setattr(media.storage, "store_asset", fail_store)
    with pytest.raises(OSError, match="storage interrupted"):
        await service.upload_product_file_version(command)
    async with use_case_transaction(db):
        pending_id = await db.scalar(
            select(ProductFileVersion.id).where(
                ProductFileVersion.request_id == command.request_id
            )
        )
    assert pending_id is not None
    target = Types.GetProductFileVersionCommand(
        product_id=product_id, file_version_id=pending_id
    )
    assert (
        await service.cleanup_product_file_version(target)
    ).reason == "awaiting_attachment"
    with pytest.raises(LookupError):
        await service.read_owned_product_file_version(
            Types.ReadOwnedProductFileVersionCommand(
                product_id=product_id, file_version_id=pending_id, owner_id=owner.id
            )
        )
    monkeypatch.setattr(media.storage, "store_asset", store_asset)
    resumed = await service.upload_product_file_version(command)
    assert resumed.file_version_id == pending_id
    assert resumed.state == Types.ProductFileVersionState.READY


async def test_references_and_retention_guard_gc(
    db: AsyncSession,
    media: CharacterMediaWorkflow,  # noqa: F811
) -> None:
    owner, _, _ = await seed(db)
    product_id = await product_for(db, owner.id)
    other_product_id = await product_for(db, owner.id)
    service = workflow(media)
    command = image_upload(product_id, owner.id)
    info = await service.upload_product_file_version(command)
    target = Types.GetProductFileVersionCommand(
        product_id=product_id, file_version_id=info.file_version_id
    )
    draft = Types.ProductFileReferenceCommand(
        product_id=product_id,
        file_version_id=info.file_version_id,
        kind="draft",
        reference_id=uuid4(),
    )
    snapshot = replace(draft, kind="snapshot", reference_id=uuid4())
    await age_reference_clock(db, info.file_version_id, timedelta(days=2))
    assert (
        await service.cleanup_product_file_version(target)
    ).reason == "awaiting_attachment"
    with pytest.raises(LookupError):
        await retain_product_file_version(
            db, replace(draft, product_id=other_product_id)
        )
    with pytest.raises(LookupError):
        await service.read_referenced_product_file_version(snapshot)
    with pytest.raises(RuntimeError, match="abort draft write"):
        async with use_case_transaction(db):
            await retain_product_file_version(db, draft)
            raise RuntimeError("abort draft write")
    assert (
        await service.cleanup_product_file_version(target)
    ).reason == "awaiting_attachment"

    assert await retain_product_file_version(db, draft) == info
    assert await retain_product_file_version(db, draft) == info
    await retain_product_file_version(db, snapshot)
    await release_product_file_version(db, draft)
    assert (await service.cleanup_product_file_version(target)).reason == "referenced"
    async with await service.read_referenced_product_file_version(snapshot) as opened:
        assert await opened.read() == b"image-one"
    with pytest.raises(LookupError):
        await service.read_referenced_product_file_version(
            replace(snapshot, product_id=other_product_id)
        )
    await release_product_file_version(db, snapshot)
    assert (await service.cleanup_product_file_version(target)).reason == "retention"
    await age_reference_clock(db, info.file_version_id, timedelta(hours=23))
    assert (await service.cleanup_product_file_version(target)).reason == "retention"
    await age_reference_clock(db, info.file_version_id, timedelta(hours=24))
    await release_product_file_version(db, snapshot)
    assert (await service.cleanup_product_file_version(target)).deleted
    assert (
        await service.cleanup_product_file_version(target)
    ).reason == "absent_or_deleted"
    with pytest.raises(LookupError):
        await retain_product_file_version(db, draft)
    replay = await service.upload_product_file_version(command)
    assert replay.file_version_id == info.file_version_id
    assert replay.state == Types.ProductFileVersionState.DELETED


async def test_cleanup_marks_deleting_before_object_io_and_can_resume(
    db: AsyncSession,
    media: CharacterMediaWorkflow,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner, _, _ = await seed(db)
    product_id = await product_for(db, owner.id)
    service = workflow(media)
    info = await service.upload_product_file_version(image_upload(product_id, owner.id))
    reference = Types.ProductFileReferenceCommand(
        product_id=product_id,
        file_version_id=info.file_version_id,
        kind="draft",
        reference_id=uuid4(),
    )
    await retain_product_file_version(db, reference)
    await release_product_file_version(db, reference)
    await age_reference_clock(db, info.file_version_id, timedelta(days=2))
    target = Types.GetProductFileVersionCommand(
        product_id=product_id, file_version_id=info.file_version_id
    )
    delete_asset = media.storage.delete_asset

    async def fail_delete(command: StorageTypes.DeleteAssetCommand) -> None:
        raise OSError("provider temporarily unavailable")

    monkeypatch.setattr(media.storage, "delete_asset", fail_delete)
    with pytest.raises(OSError, match="temporarily unavailable"):
        await service.cleanup_product_file_version(target)
    async with use_case_transaction(db):
        state = await db.scalar(
            select(ProductFileVersion.state).where(
                ProductFileVersion.id == info.file_version_id
            )
        )
    assert state == Types.ProductFileVersionState.DELETING
    with pytest.raises(LookupError):
        await retain_product_file_version(db, reference)
    monkeypatch.setattr(media.storage, "delete_asset", delete_asset)
    assert (await service.cleanup_product_file_version(target)).deleted


async def test_http_upload_import_and_private_preview(
    db: AsyncSession,
    media: CharacterMediaWorkflow,  # noqa: F811
) -> None:
    owner, character, _ = await seed(db)
    product_id = await product_for(db, owner.id)
    wrong_product_id = await product_for(db, owner.id)
    app = FastAPI()
    app.include_router(router)
    app.state.product_file_version_workflow = workflow(media)
    auth = {"owner_id": owner.id}
    app.dependency_overrides[dependencies.get_current_owner_id] = lambda: auth[
        "owner_id"
    ]
    headers = {
        "Content-Type": "image/png",
        "Idempotency-Key": str(uuid4()),
        "X-Filename": "private.png",
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        path = f"/products/{product_id}/media/uploads"
        response = await client.post(path, content=b"private", headers=headers)
        assert response.status_code == 201, response.text
        data = response.json()
        file_version_id = data["file_version_id"]
        assert data == {
            "file_version_id": file_version_id,
            "product_id": str(product_id),
            "state": "ready",
            "content_url": f"/products/{product_id}/media/{file_version_id}/content",
            "content_type": "image/png",
            "size_bytes": 7,
            "original_filename": "private.png",
        }
        assert (
            await client.post(path, content=b"private", headers=headers)
        ).json() == data
        assert (
            await client.post(path, content=b"changed", headers=headers)
        ).status_code == 409
        assert (
            await client.post(path, content=b"", headers=headers)
        ).status_code == 422
        read = await client.get(data["content_url"])
        assert read.content == b"private"
        assert read.headers["content-type"] == "image/png"
        assert read.headers["cache-control"] == "private, no-store"
        assert read.headers["x-content-type-options"] == "nosniff"
        assert (
            await client.get(
                data["content_url"].replace(str(product_id), str(wrong_product_id))
            )
        ).status_code == 404
        source = await media.upload_character_media(upload(owner, character))
        import_path = f"/products/{product_id}/media/imports"
        import_headers = {"Idempotency-Key": str(uuid4())}
        request = {"media_id": str(source.id)}
        imported = await client.post(import_path, json=request, headers=import_headers)
        assert imported.status_code == 201, imported.text
        assert imported.json()["file_version_id"] != str(source.id)
        assert (
            await client.post(
                import_path,
                json={**request, "url": "https://example.test/img"},
                headers=import_headers,
            )
        ).status_code == 422
        auth["owner_id"] = uuid4()
        assert (await client.get(data["content_url"])).status_code == 404
        assert (
            await client.post(import_path, json=request, headers=import_headers)
        ).status_code == 404
