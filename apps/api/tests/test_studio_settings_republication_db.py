"""D -> E -> D publication settings, validation, replay and atomic rollback on PG."""

from copy import deepcopy
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from test_product_integration import ready_product
from test_studio_publication import document
from test_studio_publication_db import http_app, request, save

from app.db.models.character import Character
from app.db.models.lorebook import Lorebook, LorebookEntry
from app.db.models.model_routing import Model
from app.db.models.product import Product, ProductStudioDraft
from app.db.models.snapshot.character import CharacterSnapshot
from app.db.models.snapshot.lorebook import LorebookSnapshot
from app.db.models.snapshot.product import ProductSnapshot
from app.db.transaction import use_case_transaction
from app.modules.content.product import types as ProductTypes
from app.use_cases import studio_publication as Publication

pytestmark = pytest.mark.asyncio


async def publication_state(db: AsyncSession) -> dict[str, list[dict[str, object]]]:
    """Compare stored originals/settings/snapshots/mapping/receipts after rollback."""
    tables = (
        Product,
        ProductStudioDraft,
        ProductSnapshot,
        Character,
        CharacterSnapshot,
        Lorebook,
        LorebookEntry,
        LorebookSnapshot,
    )
    async with db.begin():
        return {
            entity.__tablename__: [
                dict(row)
                for row in (
                    await db.execute(
                        select(entity.__table__).order_by(
                            *entity.__table__.primary_key.columns
                        )
                    )
                ).mappings()
            ]
            for entity in tables
        }


@pytest.mark.parametrize("change", ["model", "reasoning", "both"])
async def test_reverted_document_applies_settings_and_rolls_back_failed_receipt(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    change: str,
) -> None:
    owner, _, _, _, initial_model, _ = await ready_product(db)
    model_id = initial_model.id
    if change != "reasoning":
        async with use_case_transaction(db):
            previous = await db.get(Model, initial_model.id)
            assert previous is not None
            model = Model(
                id=uuid4(),
                provider_id=previous.provider_id,
                model_name="model-v2",
                display_name="second",
                context_window=32000,
                input_price=1,
                output_price=1,
                capabilities=deepcopy(previous.capabilities),
            )
            db.add(model)
            model_id = model.id
    effort = "low" if change == "model" else "high"
    product = uuid4()
    original, edited = document(), document()
    edited["work"]["title"] = "Temporary edit"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=http_app(db, owner.id)),
        base_url="http://studio.test",
    ) as client:
        revision = await save(client, product, None, original)
        url = f"/products/{product}/studio-publication"
        initial_request = request(revision, initial_model.id)
        first = await client.post(url, json=initial_request)
        assert first.status_code == 200
        revision = await save(client, product, revision, edited)
        revision = await save(client, product, revision, original)
        assert revision == 3
        before = await publication_state(db)
        changed_request = {
            **request(revision, model_id),
            "reasoning_effort": effort,
            "summary": "Settings changed",
            "body": "New published settings",
        }
        # Both no-op and changed-settings requests must validate a new note.
        for settings in (request(revision, initial_model.id), changed_request):
            for field in ("summary", "body"):
                invalid = await client.post(url, json={**settings, field: " \t"})
                assert invalid.status_code == 422
        invalid_model = await client.post(
            url,
            json={
                **changed_request,
                "model_id": str(uuid4()),
            },
        )
        assert invalid_model.status_code == 422
        invalid_effort = await client.post(
            url,
            json={
                **changed_request,
                "reasoning_effort": "unsupported",
            },
        )
        assert invalid_effort.status_code == 422
        assert await publication_state(db) == before

        mark = Publication.mark_studio_publication

        async def fail_after_receipt(
            session: AsyncSession,
            command: ProductTypes.MarkStudioPublicationCommand,
        ) -> ProductTypes.ReleaseInfo:
            await mark(session, command)
            raise ValueError("injected after settings, snapshot and receipt")

        with monkeypatch.context() as patch:
            patch.setattr(Publication, "mark_studio_publication", fail_after_receipt)
            failed = await client.post(url, json=changed_request)
            assert failed.status_code == 422
        assert await publication_state(db) == before

        accepted = await client.post(url, json=changed_request)
        assert accepted.status_code == 200
        assert accepted.json()["snapshot_id"] != first.json()["snapshot_id"]
        assert accepted.json()["version"] == 2
        after = await publication_state(db)
        assert len(after["product_snapshots"]) == 2
        assert (
            next(
                row
                for row in after["product_snapshots"]
                if str(row["id"]) == first.json()["snapshot_id"]
            )
            == before["product_snapshots"][0]
        )
        snapshot = next(
            row
            for row in after["product_snapshots"]
            if str(row["id"]) == accepted.json()["snapshot_id"]
        )
        assert snapshot["snapshot_data"]["model"]["id"] == str(model_id)
        assert snapshot["snapshot_data"]["model"]["reasoning_effort"] == effort
        state = next(row for row in after["products"] if row["id"] == product)
        assert (
            state["default_model_id"] == model_id
            and state["reasoning_effort"] == effort
        )
        prior_mapping = before["product_studio_drafts"][0]["publication_release"][
            "_studio"
        ]
        mapping = after["product_studio_drafts"][0]["publication_release"]["_studio"]
        for key in ("characters", "entries", "book_id"):
            assert mapping[key] == prior_mapping[key]
        assert mapping["receipts"]["1"] == prior_mapping["receipts"]["1"]
        assert (
            mapping["receipts"]["3"]["release"]["snapshot_id"]
            == accepted.json()["snapshot_id"]
        )
        for body in (changed_request, initial_request):
            replay = await client.post(url, json=body)
            assert replay.status_code == 200
            assert replay.json() == (
                accepted.json() if body == changed_request else first.json()
            )
        for field, value in (
            ("model_id", str(uuid4())),
            ("reasoning_effort", "other"),
            ("body", "Different"),
        ):
            conflict = await client.post(url, json={**changed_request, field: value})
            assert conflict.status_code == 409
        assert await publication_state(db) == after
        await save(client, product, revision, edited)
        replay = await client.post(url, json=changed_request)
        assert replay.status_code == 200 and replay.json() == accepted.json()


async def test_legacy_receipt_compares_immutable_snapshot_settings(
    db: AsyncSession,
) -> None:
    owner, _, _, _, model, _ = await ready_product(db)
    product = uuid4()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=http_app(db, owner.id)),
        base_url="http://studio.test",
    ) as client:
        revision = await save(client, product, None, document())
        url = f"/products/{product}/studio-publication"
        first = await client.post(url, json=request(revision, model.id))
        assert first.status_code == 200
        async with use_case_transaction(db):
            draft = await db.get(ProductStudioDraft, product, populate_existing=True)
            state = await db.get(Product, product, populate_existing=True)
            assert (
                draft is not None
                and draft.publication_release is not None
                and state is not None
            )
            draft.publication_release = {
                key: value
                for key, value in draft.publication_release.items()
                if key != "_studio"
            }
            # Mutable settings already match the next request, but the immutable
            # legacy snapshot still contains low. Comparing current settings fails.
            state.reasoning_effort = "high"
        changed_request = {**request(revision, model.id), "reasoning_effort": "high"}
        accepted = await client.post(url, json=changed_request)
        assert accepted.status_code == 200 and accepted.json()["version"] == 2
        assert accepted.json()["snapshot_id"] != first.json()["snapshot_id"]
        replay = await client.post(url, json=changed_request)
        assert replay.status_code == 200 and replay.json() == accepted.json()
