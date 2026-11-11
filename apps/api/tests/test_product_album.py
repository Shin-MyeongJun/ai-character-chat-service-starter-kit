"""U19 a5 album HTTP and transactional unlock contracts."""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from test_character_media import media  # noqa: F401 - parametrized storage fixture
from test_product_file_versions import image_upload, product_for, workflow
from test_product_integration import seed

from app.db.models.product import Product
from app.db.models.product_album import ProductImageUnlock
from app.db.models.snapshot.product import ProductSnapshot
from app.db.transaction import use_case_transaction
from app.http import dependencies
from app.http.media import router as media_router
from app.modules.content.character.service.workflow.media import CharacterMediaWorkflow
from app.modules.content.product import types as Types
from app.modules.content.product.router import router as product_router
from app.modules.content.product.service.command.album import unlock_product_images
from app.modules.content.product.service.command.file_versions import (
    retain_product_file_version,
)

pytestmark = pytest.mark.asyncio


def image_item(item_id: UUID, file_id: UUID, alt: str) -> Types.ProductJsonObject:
    return {
        "image_item_id": str(item_id),
        "file_version_id": str(file_id),
        "kind": "expression",
        "target": {"kind": "character", "product_character_id": str(uuid4())},
        "tags": ["smile"],
        "alt": alt,
    }


async def publish_snapshot(
    db: AsyncSession,
    product_id: UUID,
    version: int,
    items: list[Types.ProductJsonObject] | None = None,
) -> UUID:
    snapshot_id = uuid4()
    snapshot_data: Types.ProductSnapshotData = {"title": "Album"}
    if items is not None:
        snapshot_data["chat_image_items"] = items
    async with use_case_transaction(db):
        db.add(
            ProductSnapshot(
                id=snapshot_id,
                product_id=product_id,
                version=version,
                snapshot_data=dict(snapshot_data),
            )
        )
        await db.flush()
        for file_id in sorted(
            {UUID(str(item["file_version_id"])) for item in items or []}
        ):
            await retain_product_file_version(
                db,
                Types.ProductFileReferenceCommand(
                    product_id=product_id,
                    file_version_id=file_id,
                    kind="snapshot",
                    reference_id=snapshot_id,
                ),
            )
        await db.execute(
            update(Product)
            .where(Product.id == product_id)
            .values(
                latest_snapshot_id=snapshot_id, status="approved", visibility="unlisted"
            )
        )
    return snapshot_id


async def test_concurrent_unlock_preserves_first_timestamp_and_caller_rollback(
    db: AsyncSession,
) -> None:
    account, _, _ = await seed(db)
    product_id = await product_for(db, account.id)
    first_item, second_item, rolled_back_item = uuid4(), uuid4(), uuid4()
    factory = async_sessionmaker(db.bind, expire_on_commit=False)
    command = Types.UnlockProductImagesCommand(
        account_id=account.id,
        product_id=product_id,
        image_item_ids=(first_item, second_item, first_item),
    )
    first_inserted = asyncio.Event()
    second_pid: asyncio.Future[int] = asyncio.get_running_loop().create_future()

    async def unlock_first() -> dict[UUID, datetime]:
        async with factory() as session, use_case_transaction(session):
            await unlock_product_images(session, command)
            timestamps = {
                row.image_item_id: row.unlocked_at
                for row in await session.scalars(select(ProductImageUnlock))
            }
            first_inserted.set()
            pid = await second_pid
            while not await session.scalar(
                text("SELECT cardinality(pg_blocking_pids(:pid)) > 0"), {"pid": pid}
            ):
                await asyncio.sleep(0.01)
        return timestamps

    async def unlock_second() -> None:
        await first_inserted.wait()
        async with factory() as session, use_case_transaction(session):
            pid = await session.scalar(text("SELECT pg_backend_pid()"))
            assert isinstance(pid, int)
            second_pid.set_result(pid)
            await unlock_product_images(session, command)

    expected, _ = await asyncio.wait_for(
        asyncio.gather(unlock_first(), unlock_second()), timeout=10
    )
    assert expected.keys() == {first_item, second_item}
    async with factory() as session:
        async with session.begin():
            await unlock_product_images(
                session,
                Types.UnlockProductImagesCommand(
                    account_id=account.id,
                    product_id=product_id,
                    image_item_ids=(rolled_back_item,),
                ),
            )
            await session.rollback()
        rows = (await session.scalars(select(ProductImageUnlock))).all()
        assert len(rows) == 2
        assert {row.image_item_id: row.unlocked_at for row in rows} == expected


async def test_album_current_file_unlock_and_privacy(
    db: AsyncSession,
    media: CharacterMediaWorkflow,  # noqa: F811
) -> None:
    author, _, _ = await seed(db)
    reader, _, _ = await seed(db)
    other_reader, _, _ = await seed(db)
    product_id = await product_for(db, author.id)
    other_product_id = await product_for(db, author.id)
    service = workflow(media)
    first_file, replaced_file, locked_file = [
        (
            await service.upload_product_file_version(
                image_upload(product_id, author.id, body)
            )
        ).file_version_id
        for body in (b"original", b"replacement", b"locked")
    ]
    first_item, new_item = uuid4(), uuid4()
    first_snapshot = await publish_snapshot(
        db, product_id, 1, [image_item(first_item, first_file, "Original")]
    )
    path = f"/products/{product_id}/album"
    file_path = f"{path}/items/{first_item}/files/{first_file}/content"
    actor_id: UUID | None = reader.id

    async def authenticate() -> UUID:
        if actor_id is None:
            raise HTTPException(401)
        return actor_id

    async def session_dependency() -> AsyncIterator[AsyncSession]:
        async with service.session_factory() as session:
            yield session

    app = FastAPI()
    app.include_router(product_router)
    app.include_router(media_router)
    app.state.product_file_version_workflow = service
    app.dependency_overrides[dependencies.get_current_owner_id] = authenticate
    app.dependency_overrides[dependencies.get_product_session] = session_dependency
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(path)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "private, no-store"
        assert response.json() == {
            "product_id": str(product_id),
            "product_snapshot_id": str(first_snapshot),
            "available": True,
            "items": [{"image_item_id": str(first_item), "status": "locked"}],
        }
        not_found = await client.get(file_path)
        assert not_found.status_code == 404

        async with use_case_transaction(db):
            await unlock_product_images(
                db,
                Types.UnlockProductImagesCommand(
                    account_id=reader.id,
                    product_id=product_id,
                    image_item_ids=(first_item,),
                ),
            )
        original = (await client.get(path)).json()["items"][0]
        assert original["content_url"] == file_path
        assert (await client.get(file_path)).content == b"original"

        current_snapshot = await publish_snapshot(
            db,
            product_id,
            2,
            [
                image_item(first_item, replaced_file, "Replacement"),
                image_item(new_item, locked_file, "Hidden alt"),
            ],
        )
        current = (await client.get(path)).json()
        assert current["product_snapshot_id"] == str(current_snapshot)
        unlocked, locked = current["items"]
        assert unlocked == {
            "image_item_id": str(first_item),
            "status": "unlocked",
            "file_version_id": str(replaced_file),
            "alt": "Replacement",
            "unlocked_at": original["unlocked_at"],
            "content_url": f"{path}/items/{first_item}/files/{replaced_file}/content",
        }
        assert locked == {"image_item_id": str(new_item), "status": "locked"}
        current_file = await client.get(unlocked["content_url"])
        assert current_file.status_code == 200
        assert current_file.content == b"replacement"
        assert current_file.headers["content-type"] == "image/png"
        assert current_file.headers["cache-control"] == "private, no-store"
        for rejected_url in (
            file_path,
            f"{path}/items/{new_item}/files/{locked_file}/content",
            f"{path}/items/{first_item}/files/{locked_file}/content",
            unlocked["content_url"].replace(str(product_id), str(other_product_id), 1),
        ):
            rejected = await client.get(rejected_url)
            assert (rejected.status_code, rejected.json()) == (404, not_found.json())

        actor_id = other_reader.id
        assert (await client.get(unlocked["content_url"])).status_code == 404
        actor_id = None
        assert (await client.get(path)).status_code == 401
        assert (await client.get(unlocked["content_url"])).status_code == 401

        actor_id = reader.id
        async with use_case_transaction(db):
            await db.execute(
                update(ProductSnapshot)
                .where(ProductSnapshot.id == current_snapshot)
                .values(expires_at=datetime.now(UTC))
            )
        assert (await client.get(path)).json() == {
            "product_id": str(product_id),
            "product_snapshot_id": None,
            "available": False,
            "items": [],
        }
        assert (await client.get(unlocked["content_url"])).status_code == 404

        async with use_case_transaction(db):
            await db.execute(
                update(Product)
                .where(Product.id == product_id)
                .values(visibility="private")
            )
        assert (await client.get(path)).status_code == 404


async def test_unpublished_and_zero_image_album(db: AsyncSession) -> None:
    account, _, _ = await seed(db)
    product_id = await product_for(db, account.id)
    from app.modules.content.product.mapper.schema import ProductSchemaMapper
    from app.modules.content.product.service.query.album import get_product_album

    command = Types.GetProductAlbumCommand(account_id=account.id, product_id=product_id)

    async def read_album() -> dict[str, object]:
        async with use_case_transaction(db):
            info = await get_product_album(db, command)
        return ProductSchemaMapper.album_info_to_response(info).model_dump(mode="json")

    empty = {
        "product_id": str(product_id),
        "product_snapshot_id": None,
        "available": False,
        "items": [],
    }
    assert await read_album() == empty
    snapshot_id = await publish_snapshot(db, product_id, 1)
    assert await read_album() == {**empty, "product_snapshot_id": str(snapshot_id)}
