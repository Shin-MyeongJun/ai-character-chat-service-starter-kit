"""Published opening images are unlocked and read by their exact occurrence."""

from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from test_character_media import media  # noqa: F401 - pytest fixture
from test_product_file_versions import image_upload, product_for, workflow
from test_product_integration import ready_product
from test_studio_image_publication import image_document

from app.db.models.chat import Conversation
from app.db.models.product_album import ProductImageUnlock
from app.db.models.snapshot.product import ProductSnapshot, ProductSnapshotStartSet
from app.db.transaction import use_case_transaction
from app.http import dependencies
from app.http.media import router as media_router
from app.modules.chatting.conversation import types as ConversationTypes
from app.modules.chatting.conversation.router import router
from app.modules.chatting.conversation.service import command as StartService
from app.modules.content.character.service.workflow.media import CharacterMediaWorkflow
from app.modules.content.product import types as ProductTypes
from app.use_cases import studio_publication as Publication
from app.use_cases.studio_components import save_studio


@pytest.mark.asyncio
async def test_start_images_keep_selected_occurrence_across_releases(
    db: AsyncSession,
    media: CharacterMediaWorkflow,  # noqa: F811 - pytest fixture
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner, _, _, _, model, _ = await ready_product(db)
    product_id = await product_for(db, owner.id)
    files = workflow(media)
    first, replacement = [
        await files.upload_product_file_version(
            image_upload(product_id, owner.id, body)
        )
        for body in (b"first image", b"replacement image")
    ]
    selected_item, unselected_item = uuid4(), uuid4()
    document = image_document(first.file_version_id, selected_item, unselected_item)
    scenes = document["scenes"]
    scenes[0]["openingImagePlacements"] = [
        {"imageItemId": str(selected_item), "afterParagraph": 1},
        {"imageItemId": str(selected_item), "afterParagraph": 1},
    ]
    scenes.append(
        {
            **scenes[0],
            "id": "other",
            "title": "Other",
            "openingImagePlacements": [
                {"imageItemId": str(unselected_item), "afterParagraph": 0}
            ],
        }
    )
    draft = await save_studio(
        db,
        ProductTypes.SaveStudioDraftCommand(
            product_id=product_id,
            owner_id=owner.id,
            expected_revision=None,
            document=document,
        ),
    )
    publish = Publication.PublishStudioCommand(
        product_id, owner.id, draft.revision, model.id, "low", "Initial", "Two openings"
    )
    initial = await Publication.publish_studio(db, publish)
    async with db.begin():
        start_id = await db.scalar(
            select(ProductSnapshotStartSet.id).where(
                ProductSnapshotStartSet.product_snapshot_id == initial.snapshot_id,
                ProductSnapshotStartSet.title == "Arrival",
            )
        )
    assert start_id is not None

    async def fail_after_unlock(
        session: AsyncSession, command: ProductTypes.MarkStatisticsDirtyCommand
    ) -> None:
        assert await session.scalar(select(func.count()).select_from(Conversation)) == 1
        assert (
            await session.scalar(select(func.count()).select_from(ProductImageUnlock))
            == 1
        )
        raise RuntimeError("Fail before commit")

    command = ConversationTypes.StartConversationCommand(
        product_id=product_id, user_id=owner.id, start_set_id=start_id
    )
    with monkeypatch.context() as patches:
        patches.setattr(StartService, "mark_statistics_dirty", fail_after_unlock)
        with pytest.raises(RuntimeError, match="Fail before commit"):
            await StartService.start_conversation(db, command)
    async with db.begin():
        assert await db.scalar(select(func.count()).select_from(Conversation)) == 0
        assert (
            await db.scalar(select(func.count()).select_from(ProductImageUnlock)) == 0
        )

    actor_id = owner.id

    async def authenticate() -> UUID:
        return actor_id

    async def session_dependency() -> AsyncIterator[AsyncSession]:
        async with files.session_factory() as session:
            yield session

    app = FastAPI()
    app.include_router(router)
    app.include_router(media_router)
    app.state.product_file_version_workflow = files
    app.dependency_overrides[dependencies.get_current_owner_id] = authenticate
    app.dependency_overrides[dependencies.get_product_session] = session_dependency
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        rejected = await client.post(
            "/conversations", json={"product_id": str(product_id)}
        )
        assert rejected.status_code == 422
        created = await client.post(
            "/conversations",
            json={"product_id": str(product_id), "start_set_id": str(start_id)},
        )
        assert created.status_code == 201
        path = f"/conversations/{created.json()['id']}/start"
        opened = await client.get(path)
        assert opened.status_code == 200
        initial_body = opened.json()
        assert initial_body["initial_snapshot_id"] == str(initial.snapshot_id)
        assert initial_body["opening_message"] == "Welcome.\r\n \r\nCome inside."
        image = {
            "type": "image",
            "image_item_id": str(selected_item),
            "file_version_id": str(first.file_version_id),
            "alt": "Hero",
        }
        image_path = f"{path}/blocks/1/content"
        assert initial_body["content_blocks"] == [
            {"type": "text", "text": "Welcome.\r\n \r\n"},
            {**image, "content_url": image_path},
            {**image, "content_url": f"{path}/blocks/2/content"},
            {"type": "text", "text": "Come inside."},
        ]
        response = await client.get(image_path)
        assert response.status_code == 200 and response.content == b"first image"
        assert response.headers["content-type"] == "image/png"
        assert response.headers["cache-control"] == "private, no-store"
        for index in (-1, 0, 4):
            assert (
                await client.get(f"{path}/blocks/{index}/content")
            ).status_code == 404

        actor_id = uuid4()
        assert (await client.get(path)).status_code == 404
        assert (await client.get(image_path)).status_code == 404
        actor_id = owner.id

        async with db.begin():
            unlocked = (await db.scalars(select(ProductImageUnlock))).one()
            assert (
                unlocked.account_id == owner.id
                and unlocked.image_item_id == selected_item
            )
            unlocked_at = unlocked.unlocked_at

        document["chatImageItems"][0]["fileVersionId"] = str(
            replacement.file_version_id
        )
        updated = await save_studio(
            db,
            ProductTypes.SaveStudioDraftCommand(
                product_id=product_id,
                owner_id=owner.id,
                expected_revision=draft.revision,
                document=document,
            ),
        )
        latest = await Publication.publish_studio(
            db, replace(publish, expected_revision=updated.revision)
        )
        switched = await client.post(
            path.removesuffix("/start") + "/version",
            json={"target_snapshot_id": str(latest.snapshot_id)},
        )
        assert switched.status_code == 200 and switched.json()["changed"] is True
        async with use_case_transaction(db):
            expired = await db.get(ProductSnapshot, initial.snapshot_id)
            assert expired is not None
            expired.expires_at = datetime.now(UTC) - timedelta(days=1)

        reread = (await client.get(path)).json()
        assert reread["initial_snapshot_id"] == initial_body["initial_snapshot_id"]
        assert reread["content_blocks"] == initial_body["content_blocks"]
        assert (await client.get(image_path)).content == b"first image"
        async with db.begin():
            unlocked = (await db.scalars(select(ProductImageUnlock))).one()
            assert (
                unlocked.image_item_id == selected_item
                and unlocked.unlocked_at == unlocked_at
            )
