"""Publication freezes Studio images and retains their exact file versions."""

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from test_character_media import media  # noqa: F401 - pytest fixture
from test_product_file_versions import image_upload, product_for, workflow
from test_product_integration import ready_product
from test_studio_publication import document

from app.db.models.product import Product, ProductStudioDraft
from app.db.models.product_file_version import ProductFileReference
from app.db.models.snapshot.lorebook import LorebookSnapshot
from app.db.models.snapshot.product import (
    ProductSnapshot,
    ProductSnapshotCharacter,
    ProductSnapshotStartSet,
)
from app.db.transaction import use_case_transaction
from app.modules.content.character.service.workflow.media import CharacterMediaWorkflow
from app.modules.content.product import types as Types
from app.modules.content.product.service.studio_images import (
    prepare_studio_image_publication,
)
from app.use_cases import studio_publication as Publication
from app.use_cases.studio_components import save_studio


def image_document(
    file_id: UUID, item_id: UUID, lore_id: UUID
) -> Types.ProductJsonObject:
    value = document()
    value["chatImageItems"] = [
        {
            "imageItemId": str(item_id),
            "fileVersionId": str(file_id),
            "target": {"kind": "character", "id": "hero"},
            "kind": "expression",
            "tags": ["smile"],
            "alt": "Hero",
        },
        {
            "imageItemId": str(lore_id),
            "fileVersionId": str(file_id),
            "target": {"kind": "lore_entry", "id": "world"},
            "kind": "situation",
            "tags": ["smile"],
            "alt": "World",
        },
    ]
    value["scenes"][0]["opening"] = "Welcome.\r\n \r\nCome inside."
    value["scenes"][0]["openingImagePlacements"] = [
        {"imageItemId": str(lore_id), "afterParagraph": 0},
        {"imageItemId": str(item_id), "afterParagraph": 1},
        {"imageItemId": str(lore_id), "afterParagraph": 1},
    ]
    return value


def test_image_digest_tracks_conditions_files_and_placement_order() -> None:
    file_id, item_id, lore_id = uuid4(), uuid4(), uuid4()
    original = image_document(file_id, item_id, lore_id)
    prepared = prepare_studio_image_publication(original)
    assert prepared is not None
    assert prepared.file_version_ids == (file_id,)
    blocks = prepared.start_blocks_by_scene_id["scene"]
    assert blocks[1] == {"type": "text", "text": "Welcome.\r\n \r\n"}
    assert blocks[4] == {"type": "text", "text": "Come inside."}
    assert blocks[0] == blocks[3]

    conditions = image_document(file_id, item_id, lore_id)
    conditions["chatImageItems"][0]["tags"] = ["surprise"]
    positions = image_document(file_id, item_id, lore_id)
    positions["scenes"][0]["openingImagePlacements"][1]["afterParagraph"] = 2
    for edited in (conditions, positions, image_document(uuid4(), item_id, lore_id)):
        changed = prepare_studio_image_publication(edited)
        assert changed is not None
        assert changed.digest != prepared.digest


@pytest.mark.asyncio
async def test_publication_freezes_and_retains_files_across_releases(
    db: AsyncSession,
    media: CharacterMediaWorkflow,  # noqa: F811 - pytest fixture
) -> None:
    owner, _, _, _, model, _ = await ready_product(db)
    product_id = await product_for(db, owner.id)
    files = workflow(media)
    first = await files.upload_product_file_version(image_upload(product_id, owner.id))
    second = await files.upload_product_file_version(
        image_upload(product_id, owner.id, b"replacement")
    )
    item_id, lore_id = uuid4(), uuid4()

    async def save(revision: int | None, value: Types.ProductJsonObject) -> int:
        draft = await save_studio(
            db,
            Types.SaveStudioDraftCommand(
                product_id=product_id,
                owner_id=owner.id,
                expected_revision=revision,
                document=value,
            ),
        )
        return draft.revision

    original = image_document(first.file_version_id, item_id, lore_id)
    revision = await save(None, original)
    request = Publication.PublishStudioCommand(
        product_id, owner.id, revision, model.id, "low", "Initial", "Images ready"
    )
    initial = await Publication.publish_studio(db, request)
    conditions = image_document(first.file_version_id, item_id, lore_id)
    conditions["chatImageItems"][0]["tags"] = ["surprise"]
    revision = await save(revision, conditions)
    changed = await Publication.publish_studio(
        db, replace(request, expected_revision=revision)
    )
    assert changed.change_kind == "content"
    replacement = image_document(second.file_version_id, item_id, lore_id)
    replacement["chatImageItems"][0]["tags"] = ["surprise"]
    revision = await save(revision, replacement)
    replaced = await Publication.publish_studio(
        db, replace(request, expected_revision=revision)
    )
    assert replaced.change_kind == "content"
    assert (initial.version, changed.version, replaced.version) == (1, 2, 3)
    assert await Publication.publish_studio(db, request) == initial
    with pytest.raises(Types.StudioDraftConflictError):
        await Publication.publish_studio(db, replace(request, summary="Other"))

    async with use_case_transaction(db):
        original_snapshot = await db.get(ProductSnapshot, initial.snapshot_id)
        changed_snapshot = await db.get(ProductSnapshot, changed.snapshot_id)
        latest = await db.get(ProductSnapshot, replaced.snapshot_id)
        assert (
            original_snapshot is not None
            and changed_snapshot is not None
            and latest is not None
        )
        initial_items = original_snapshot.snapshot_data["chat_image_items"]
        latest_items = latest.snapshot_data["chat_image_items"]
        assert initial_items[0]["tags"] == ["smile"]
        assert changed_snapshot.snapshot_data["chat_image_items"][0]["tags"] == [
            "surprise"
        ]
        assert (
            initial_items[0]["image_item_id"]
            == latest_items[0]["image_item_id"]
            == str(item_id)
        )
        assert initial_items[0]["file_version_id"] == str(first.file_version_id)
        assert latest_items[0]["file_version_id"] == str(second.file_version_id)
        slot = await db.scalar(
            select(ProductSnapshotCharacter).where(
                ProductSnapshotCharacter.product_snapshot_id == latest.id
            )
        )
        start = await db.scalar(
            select(ProductSnapshotStartSet).where(
                ProductSnapshotStartSet.product_snapshot_id == latest.id
            )
        )
        assert slot is not None and start is not None
        assert latest_items[0]["target"]["product_character_id"] == str(slot.id)
        lore_target = latest_items[1]["target"]
        lore_snapshot = await db.get(
            LorebookSnapshot, UUID(lore_target["lorebook_snapshot_id"])
        )
        assert lore_snapshot is not None
        assert any(
            row["id"] == lore_target["lore_entry_id"] and row["title"] == "World"
            for row in lore_snapshot.snapshot_data["entries"]
        )
        assert latest.snapshot_data["starts"][0]["start_set_id"] == str(start.id)
        assert latest.snapshot_data["starts"][0]["content_blocks"][0][
            "file_version_id"
        ] == str(second.file_version_id)
        assert original_snapshot.snapshot_data["starts"][0]["content_blocks"][0][
            "file_version_id"
        ] == str(first.file_version_id)
        original_snapshot.expires_at = datetime.now(UTC)
        references = (
            await db.scalars(
                select(ProductFileReference).where(
                    ProductFileReference.kind == "snapshot"
                )
            )
        ).all()
        assert {(ref.file_version_id, ref.reference_id) for ref in references} == {
            (first.file_version_id, initial.snapshot_id),
            (first.file_version_id, changed.snapshot_id),
            (second.file_version_id, replaced.snapshot_id),
        }
    target = Types.GetProductFileVersionCommand(
        product_id=product_id, file_version_id=first.file_version_id
    )
    assert (await files.cleanup_product_file_version(target)).reason == "referenced"
    async with await files.read_referenced_product_file_version(
        Types.ProductFileReferenceCommand(
            product_id=product_id,
            file_version_id=first.file_version_id,
            kind="snapshot",
            reference_id=initial.snapshot_id,
        )
    ) as reader:
        assert await reader.read() == b"image-one"


@pytest.mark.asyncio
async def test_publication_rejects_foreign_file_and_rolls_back_failed_receipt(
    db: AsyncSession,
    media: CharacterMediaWorkflow,  # noqa: F811 - pytest fixture
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner, _, _, _, model, _ = await ready_product(db)
    product_id = await product_for(db, owner.id)
    foreign_product_id = await product_for(db, owner.id)
    files = workflow(media)
    own = await files.upload_product_file_version(image_upload(product_id, owner.id))
    foreign = await files.upload_product_file_version(
        image_upload(foreign_product_id, owner.id)
    )
    item_id, lore_id = uuid4(), uuid4()
    saved = await save_studio(
        db,
        Types.SaveStudioDraftCommand(
            product_id=product_id,
            owner_id=owner.id,
            expected_revision=None,
            document=image_document(own.file_version_id, item_id, lore_id),
        ),
    )
    request = Publication.PublishStudioCommand(
        product_id, owner.id, saved.revision, model.id, "low", "First", "Images ready"
    )

    async def write_draft(file_id: UUID) -> None:
        async with use_case_transaction(db):
            draft = await db.get(ProductStudioDraft, product_id)
            assert draft is not None
            draft.document = image_document(file_id, item_id, lore_id)

    await write_draft(foreign.file_version_id)
    with pytest.raises(LookupError, match="File version not found"):
        await Publication.publish_studio(db, request)
    await write_draft(own.file_version_id)

    async def fail_receipt(
        _session: AsyncSession, _command: Types.MarkStudioPublicationCommand
    ) -> None:
        raise RuntimeError("receipt write failed")

    with monkeypatch.context() as patch:
        patch.setattr(Publication, "mark_studio_publication", fail_receipt)
        with pytest.raises(RuntimeError, match="receipt write failed"):
            await Publication.publish_studio(db, request)
    async with use_case_transaction(db):
        product = await db.get(Product, product_id)
        draft = await db.get(ProductStudioDraft, product_id)
        assert product is not None and product.latest_snapshot_id is None
        assert draft is not None and draft.publication_release is None
        assert (
            await db.scalar(
                select(ProductSnapshot).where(ProductSnapshot.product_id == product_id)
            )
            is None
        )
        assert (
            await db.scalar(
                select(ProductFileReference).where(
                    ProductFileReference.kind == "snapshot"
                )
            )
            is None
        )
    assert (await Publication.publish_studio(db, request)).version == 1
