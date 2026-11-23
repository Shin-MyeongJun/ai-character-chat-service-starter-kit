"""Exercise owner publication and reader image access across both HTTP routes."""

from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from test_character_media import media  # noqa: F401 - parametrized storage fixture
from test_product_file_versions import image_upload, product_for, workflow
from test_product_integration import ready_product, seed
from test_studio_image_publication import image_document
from test_studio_publication_db import http_app, request, save

from app.db.models.lorebook import LorebookEntry
from app.db.models.product import Product, ProductCharacter, ProductStartSet
from app.db.models.product_file_version import ProductFileReference
from app.db.models.product_release import ProductReleaseNote
from app.db.models.snapshot.product import (
    ProductSnapshot,
    ProductSnapshotCharacter,
    ProductSnapshotLorebook,
)
from app.http.media import router as media_router
from app.modules.chatting.conversation.router import router as conversation_router
from app.modules.content.character.service.workflow.media import CharacterMediaWorkflow
from app.modules.content.product.router import router as product_router


@pytest.mark.asyncio
async def test_regular_release_inherits_published_images_until_studio_replaces_or_clears(
    db: AsyncSession,
    media: CharacterMediaWorkflow,  # noqa: F811
) -> None:
    owner, _, _, _, model, _ = await ready_product(db)
    reader, _, _ = await seed(db)
    product_id = await product_for(db, owner.id)
    files = workflow(media)
    file_a, file_b = [
        (
            await files.upload_product_file_version(
                image_upload(product_id, owner.id, data)
            )
        ).file_version_id
        for data in (b"published A", b"draft B")
    ]
    hero, lore = uuid4(), uuid4()
    app = http_app(db, owner.id)
    app.include_router(product_router)
    reader_app = http_app(db, reader.id)
    reader_app.include_router(product_router)
    reader_app.include_router(conversation_router)
    reader_app.include_router(media_router)
    reader_app.state.product_file_version_workflow = files
    base = f"/products/{product_id}"
    note = {"summary": "Regular", "body": "Publish current product"}
    async with (
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as author,
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=reader_app), base_url="http://test"
        ) as client,
    ):

        async def open_room(snapshot_id: str) -> str:
            response = await client.post(
                "/conversations", json={"product_id": str(product_id)}
            )
            assert response.status_code == 201, response.text
            start = (
                await client.get(f"/conversations/{response.json()['id']}/start")
            ).json()
            assert start["initial_snapshot_id"] == snapshot_id
            return start["content_blocks"][2]["content_url"]

        document = image_document(file_a, hero, lore)
        document["work"]["visibility"] = "전체 공개"
        revision = await save(author, product_id, None, document)
        original_request = request(revision, model.id)
        original = await author.post(
            f"{base}/studio-publication", json=original_request
        )
        assert original.status_code == 200, original.text
        async with db.begin():
            await db.execute(
                update(Product)
                .where(Product.id == product_id)
                .values(status="approved")
            )
        old_file_url = await open_room(original.json()["snapshot_id"])
        original_album = (await client.get(f"{base}/album")).json()["items"]
        assert [item["file_version_id"] for item in original_album] == [str(file_a)] * 2

        for item in document["chatImageItems"]:
            item["fileVersionId"] = str(file_b)
        revision = await save(author, product_id, revision, document)
        regular = await author.post(f"{base}/releases", json=note)
        assert regular.status_code == 201, regular.text
        regular_id = regular.json()["snapshot_id"]
        album = (await client.get(f"{base}/album")).json()
        assert album["product_snapshot_id"] == regular_id
        assert album["items"] == original_album
        assert (
            await client.get(f"{base}/album/items/{hero}/files/{file_b}/content")
        ).status_code == 404
        assert regular.json()["change_kind"] == "media"
        assert (
            await client.get(original_album[0]["content_url"])
        ).content == b"published A"
        new_file_url = await open_room(regular_id)
        assert (await client.get(new_file_url)).content == b"published A"
        async with db.begin():
            snapshot = await db.get(ProductSnapshot, UUID(regular_id))
            assert snapshot is not None
            slot_id = await db.scalar(
                select(ProductSnapshotCharacter.id).where(
                    ProductSnapshotCharacter.product_snapshot_id == snapshot.id
                )
            )
            character, world = snapshot.snapshot_data["chat_image_items"]
            assert character["target"]["product_character_id"] == str(slot_id)
            book_id = await db.scalar(
                select(ProductSnapshotLorebook.lorebook_snapshot_id).where(
                    ProductSnapshotLorebook.product_snapshot_id == snapshot.id
                )
            )
            assert world["target"]["lorebook_snapshot_id"] == str(book_id)
            assert (
                await db.scalars(
                    select(ProductFileReference.file_version_id).where(
                        ProductFileReference.kind == "snapshot",
                        ProductFileReference.reference_id == snapshot.id,
                    )
                )
            ).all() == [file_a]

        published = await author.post(
            f"{base}/studio-publication", json=request(revision, model.id)
        )
        assert published.status_code == 200 and published.json()["version"] == 3
        album = (await client.get(f"{base}/album")).json()
        assert album["product_snapshot_id"] == published.json()["snapshot_id"]
        for before, after in zip(original_album, album["items"], strict=True):
            assert after["image_item_id"] == before["image_item_id"]
            assert after["unlocked_at"] == before["unlocked_at"]
            assert after["file_version_id"] == str(file_b)
            assert (await client.get(after["content_url"])).content == b"draft B"
        for url in (old_file_url, new_file_url):
            assert (await client.get(url)).content == b"published A"

        document["chatImageItems"] = []
        document["scenes"][0]["openingImagePlacements"] = []
        revision = await save(author, product_id, revision, document)
        cleared = await author.post(
            f"{base}/studio-publication", json=request(revision, model.id)
        )
        assert cleared.status_code == 200 and cleared.json()["version"] == 4
        assert (await client.get(f"{base}/album")).json()["items"] == []
        await save(
            author, product_id, revision, image_document(file_b, uuid4(), uuid4())
        )
        plain = await author.post(f"{base}/releases", json=note)
        assert plain.status_code == 201 and plain.json()["version"] == 5
        replay = await author.post(f"{base}/studio-publication", json=original_request)
        assert replay.json() == original.json()
        album = (await client.get(f"{base}/album")).json()
        assert album["product_snapshot_id"] == plain.json()["snapshot_id"]
        assert album["items"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "missing", ["character", "lore entry", "start option", "opening text"]
)
async def test_unmatched_published_images_roll_back_regular_release(
    db: AsyncSession,
    media: CharacterMediaWorkflow,  # noqa: F811
    missing: str,
) -> None:
    owner, other_character, _, _, model, _ = await ready_product(db)
    product_id = await product_for(db, owner.id)
    files = workflow(media)
    uploaded = await files.upload_product_file_version(
        image_upload(product_id, owner.id)
    )
    document = image_document(uploaded.file_version_id, uuid4(), uuid4())
    document["scenes"].append({**document["scenes"][0], "id": "second"})
    app = http_app(db, owner.id)
    app.include_router(product_router)
    base = f"/products/{product_id}"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        revision = await save(client, product_id, None, document)
        initial = await client.post(
            f"{base}/studio-publication", json=request(revision, model.id)
        )
        assert initial.status_code == 200
        original_id = UUID(initial.json()["snapshot_id"])
        async with db.begin():
            snapshot = await db.get(ProductSnapshot, original_id)
            assert snapshot is not None
            start = (
                await db.scalars(
                    select(ProductStartSet)
                    .where(ProductStartSet.product_id == product_id)
                    .order_by(ProductStartSet.sort_order)
                )
            ).first()
            assert start is not None
            if missing == "character":
                await db.execute(
                    update(ProductCharacter)
                    .where(ProductCharacter.product_id == product_id)
                    .values(character_id=other_character.id)
                )
            elif missing == "lore entry":
                target = snapshot.snapshot_data["chat_image_items"][1]["target"]
                await db.execute(
                    delete(LorebookEntry).where(
                        LorebookEntry.id == UUID(target["lore_entry_id"])
                    )
                )
            elif missing == "start option":
                await db.delete(start)
            else:
                await db.execute(
                    update(LorebookEntry)
                    .where(LorebookEntry.id == start.entry_id)
                    .values(metadata_={"studio_scene_v1": {"opening": "New opening"}})
                )

        failed = await client.post(
            f"{base}/releases",
            json={"summary": "Changed", "body": "Changed composition"},
        )
        assert failed.status_code == 422
        assert (
            missing in failed.json()["detail"] and "Studio" in failed.json()["detail"]
        )
        async with db.begin():
            assert (
                await db.scalar(
                    select(Product.latest_snapshot_id).where(Product.id == product_id)
                )
                == original_id
            )
            assert (
                await db.scalars(
                    select(ProductSnapshot.id).where(
                        ProductSnapshot.product_id == product_id
                    )
                )
            ).all() == [original_id]
            assert (
                await db.scalars(select(ProductReleaseNote.product_snapshot_id))
            ).all() == [original_id]
            assert (
                await db.execute(
                    select(
                        ProductFileReference.reference_id,
                        ProductFileReference.file_version_id,
                    ).where(ProductFileReference.kind == "snapshot")
                )
            ).all() == [(original_id, uploaded.file_version_id)]
