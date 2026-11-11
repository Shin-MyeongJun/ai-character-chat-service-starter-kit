"""A3 references and draft revision share the same PostgreSQL transaction."""

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from test_character_media import media  # noqa: F401 - pytest fixture
from test_product_file_versions import image_upload, product_for, workflow
from test_product_integration import seed
from test_studio_locking_db import document

from app.db.models.product_file_version import ProductFileReference
from app.db.transaction import use_case_transaction
from app.http import dependencies
from app.http.media import router as MediaRouter
from app.http.studio_publication import router as StudioRouter
from app.modules.content.character.service.workflow.media import CharacterMediaWorkflow
from app.modules.content.product import types as Types
from app.modules.content.product.mapper.schema import ProductSchemaMapper
from app.modules.content.product.router import router as ProductRouter
from app.modules.content.product.service.command import studio
from app.modules.content.product.service.query.studio import get_studio_draft
from app.use_cases.studio_components import save_studio


@pytest.mark.asyncio
async def test_studio_image_cas_pins_shared_files_and_rolls_back_failed_attachment(
    db: AsyncSession,
    media: CharacterMediaWorkflow,  # noqa: F811 - pytest fixture
) -> None:
    owner, _, _ = await seed(db)
    product_id = await product_for(db, owner.id)
    other_id = await product_for(db, owner.id)
    files = workflow(media)
    original = await files.upload_product_file_version(
        image_upload(product_id, owner.id)
    )
    replacement = await files.upload_product_file_version(
        image_upload(product_id, owner.id, b"new")
    )
    foreign = await files.upload_product_file_version(image_upload(other_id, owner.id))
    first_id, second_id = uuid4(), uuid4()

    def image(item_id: UUID, file_id: UUID) -> Types.ProductJsonObject:
        return {
            "imageItemId": str(item_id),
            "fileVersionId": str(file_id),
            "target": {"kind": "character", "id": "repairer"},
            "kind": "expression",
            "tags": [" 미소 ", "미소"],
            "alt": "수리공이 미소 짓는다",
        }

    def draft(*items: Types.ProductJsonObject) -> Types.ProductJsonObject:
        return {
            **document(),
            "characters": [{"id": "repairer"}],
            "chatImageItems": list(items),
        }

    async def save(
        revision: int | None, value: Types.ProductJsonObject
    ) -> Types.StudioDraftInfo:
        return await save_studio(
            db,
            Types.SaveStudioDraftCommand(
                product_id=product_id,
                owner_id=owner.id,
                expected_revision=revision,
                document=value,
            ),
        )

    async def references() -> set[UUID]:
        async with use_case_transaction(db):
            return set(
                await db.scalars(
                    select(ProductFileReference.file_version_id).where(
                        ProductFileReference.kind == "draft",
                        ProductFileReference.reference_id == product_id,
                    )
                )
            )

    legacy = await save(None, document())
    assert "chatImageItems" not in legacy.document
    first, second = (
        image(first_id, original.file_version_id),
        image(second_id, original.file_version_id),
    )
    saved = await save(legacy.revision, draft(first, second))
    assert await references() == {original.file_version_id}
    assert (
        await save(legacy.revision, draft(first, second))
    ).revision == saved.revision

    with pytest.raises(Types.StudioDraftConflictError):
        await save(legacy.revision, draft(image(first_id, replacement.file_version_id)))
    with pytest.raises(LookupError):
        await save(
            saved.revision,
            draft(
                image(first_id, replacement.file_version_id),
                image(second_id, foreign.file_version_id),
            ),
        )
    assert await references() == {original.file_version_id}
    with pytest.raises(LookupError):
        await save(
            saved.revision,
            draft(
                image(first_id, replacement.file_version_id),
                image(second_id, UUID(int=(1 << 128) - 1)),
            ),
        )
    assert await references() == {original.file_version_id}

    swapped = await save(
        saved.revision, draft(image(first_id, replacement.file_version_id), second)
    )
    assert await references() == {original.file_version_id, replacement.file_version_id}
    latest = await save(
        swapped.revision, draft(image(first_id, replacement.file_version_id))
    )
    assert await references() == {replacement.file_version_id}
    with pytest.raises(ValueError, match="cannot be reused"):
        await save(latest.revision, draft(second))

    async with AsyncSession(db.bind) as reopened:
        remote = await get_studio_draft(
            reopened, Types.GetStudioDraftCommand(product_id, owner.id)
        )
        dto = ProductSchemaMapper.studio_draft_info_to_response(remote)
        assert dto.revision == latest.revision
        assert dto.document["chatImageItems"] == [
            {
                **image(first_id, replacement.file_version_id),
                "tags": ["미소"],
            }
        ]
        assert Types.RETIRED_STUDIO_IMAGE_ITEMS not in dto.document


@pytest.mark.asyncio
async def test_studio_image_reference_locks_follow_uuid_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    retain, release = AsyncMock(), AsyncMock()
    operations: list[tuple[UUID, str, UUID]] = []

    async def record(
        _session: AsyncSession, command: Types.ProductFileReferenceCommand
    ) -> None:
        operations.append((command.file_version_id, command.kind, command.reference_id))

    retain.side_effect = release.side_effect = record
    monkeypatch.setattr(
        studio.FileVersionsCommandService, "retain_product_file_version", retain
    )
    monkeypatch.setattr(
        studio.FileVersionsCommandService, "release_product_file_version", release
    )
    first, second, third = (UUID(int=value) for value in (1, 2, 3))
    product_id = uuid4()
    async with AsyncSession() as session, use_case_transaction(session):
        await studio._sync_studio_file_references(
            session, product_id, {third, first}, {third, second}
        )
    assert operations == [
        (value, "draft", product_id) for value in (first, second, third)
    ]


@pytest.mark.asyncio
async def test_studio_image_http_draft_survives_partial_upload_and_reconnect(
    db: AsyncSession,
    media: CharacterMediaWorkflow,  # noqa: F811 - pytest fixture
) -> None:
    owner, _, _ = await seed(db)
    product_id = await product_for(db, owner.id)
    app = FastAPI()
    app.include_router(MediaRouter)
    app.include_router(StudioRouter)
    app.include_router(ProductRouter)
    app.state.product_file_version_workflow = workflow(media)

    async def session_dependency() -> AsyncIterator[AsyncSession]:
        async with AsyncSession(db.bind, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[dependencies.get_product_session] = session_dependency
    app.dependency_overrides[dependencies.get_current_owner_id] = lambda: owner.id
    transport = httpx.ASGITransport(app=app)
    path = f"/products/{product_id}"
    start = {"id": "arrival", "opening": "수리점 문이 열렸다."}
    legacy = {
        **document(),
        "work": {
            "title": "수리점",
            "introduction": "",
            "visibility": "비공개",
            "defaultSceneId": "arrival",
        },
        "characters": [{"id": "repairer"}],
        "lorebooks": [{"id": "workshop"}],
        "scenes": [start],
    }
    headers = {
        "Idempotency-Key": str(uuid4()),
        "Content-Type": "image/png",
        "X-Filename": "workshop.png",
    }
    async with httpx.AsyncClient(
        transport=transport, base_url="http://studio.test"
    ) as client:
        initial = await client.put(
            f"{path}/studio-draft", json={"expected_revision": None, "document": legacy}
        )
        assert initial.status_code == 200, initial.text
        assert initial.json()["document"] == legacy
        uploaded = await client.post(
            f"{path}/media/uploads", headers=headers, content=b"workshop"
        )
        assert uploaded.status_code == 201, uploaded.text
        failure = await client.post(
            f"{path}/media/uploads",
            headers={**headers, "Idempotency-Key": str(uuid4())},
            content=b"",
        )
        assert failure.status_code == 422
        assert (await client.get(f"{path}/studio-draft")).json() == initial.json()

    async with httpx.AsyncClient(
        transport=transport, base_url="http://studio.test"
    ) as client:
        replay = await client.post(
            f"{path}/media/uploads", headers=headers, content=b"workshop"
        )
        assert replay.json() == uploaded.json()
        item = {
            "imageItemId": "20000000-0000-4000-8000-000000000002",
            "fileVersionId": replay.json()["file_version_id"],
            "target": {"kind": "lore_entry", "id": "workshop"},
            "kind": "situation",
            "tags": ["수리점"],
            "alt": "등불이 켜진 수리점",
        }
        placement = {"imageItemId": item["imageItemId"], "afterParagraph": 1}
        authored = {
            **legacy,
            "chatImageItems": [item],
            "scenes": [{**start, "openingImagePlacements": [placement]}],
        }
        payload = {
            "expected_revision": initial.json()["revision"],
            "document": authored,
        }
        saved = await client.put(f"{path}/studio-draft", json=payload)
        assert saved.status_code == 200, saved.text
        assert (
            await client.put(f"{path}/studio-draft", json=payload)
        ).json() == saved.json()
        invalid = {
            **authored,
            "scenes": [
                {
                    **start,
                    "openingImagePlacements": [{**placement, "afterParagraph": 2}],
                }
            ],
        }
        bad_save = await client.put(
            f"{path}/studio-draft",
            json={
                "expected_revision": saved.json()["revision"],
                "document": invalid,
            },
        )
        assert bad_save.status_code == 422, bad_save.text

    async with httpx.AsyncClient(
        transport=transport, base_url="http://studio.test"
    ) as client:
        restored = await client.get(f"{path}/studio-draft")
        assert restored.json() == saved.json()
        assert restored.json()["document"] == authored
        preview = await client.get(replay.json()["content_url"])
        assert preview.content == b"workshop"
        assert preview.headers["cache-control"] == "private, no-store"
