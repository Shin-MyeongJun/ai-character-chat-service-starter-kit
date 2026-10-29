"""Product value contracts preserve IDs, nullable titles and detached JSON."""

from dataclasses import asdict
from datetime import UTC, date, datetime
from uuid import uuid4

from app.db.models.product import (
    ProductCharacter,
    ProductLorebook,
    ProductLorebookCharacter,
    ProductStudioDraft,
)
from app.db.models.product_statistics import ProductVersionDailyStats
from app.modules.content.product import types
from app.modules.content.product.mapper import persistence
from app.modules.content.product.repository.composition import ProductCompositionRow


def test_composition_uses_source_ids_and_preserves_link_order_and_metadata():
    first = ProductCharacter(
        id=uuid4(), character_id=uuid4(), role_order=1, role_name=None, is_primary=False
    )
    second = ProductCharacter(
        id=uuid4(),
        character_id=uuid4(),
        role_order=0,
        role_name="Lead",
        is_primary=True,
    )
    book = ProductLorebook(
        id=uuid4(),
        lorebook_id=uuid4(),
        role="main",
        priority=7,
        is_required=False,
        scope="selected",
    )
    links = [
        ProductLorebookCharacter(
            product_character_id=character.id, product_lorebook_id=book.id
        )
        for character in (second, first)
    ]
    row = ProductCompositionRow([first, second], [book], links)
    info = persistence.product_composition_row_to_info(row)
    state = persistence.product_composition_row_to_state_info(row)
    assert [item.character_id for item in info.characters] == [
        first.character_id,
        second.character_id,
    ]
    assert info.lorebooks[0] == types.LorebookSelection(
        lorebook_id=book.lorebook_id,
        scope="selected",
        character_ids=(second.character_id, first.character_id),
        role="main",
        priority=7,
        is_required=False,
    )
    assert state.characters[0].id == first.id
    assert state.characters[0].character_id == first.character_id
    assert state.characters[0].role_name is None
    assert state.books[0].id == book.id
    assert [item.product_character_id for item in state.targets] == [
        second.id,
        first.id,
    ]


def test_studio_draft_info_isolates_document_and_publication_receipt():
    entity = ProductStudioDraft(
        product_id=uuid4(),
        revision=4,
        document={"version": 2, "work": {"tags": ["Fantasy"], "opening": None}},
        content_digest="document",
        publication_digest="published",
        publication_release={"version": 1, "_studio": {"characters": ["original"]}},
        updated_at=datetime.now(UTC),
    )
    info = persistence.studio_draft_entity_to_info(entity)
    assert info is not None
    assert info.product_id == entity.product_id and info.revision == 4
    assert info.content_digest == "document" and info.publication_digest == "published"
    assert info.document == entity.document
    assert info.publication_release == entity.publication_release
    info.document["work"]["tags"].append("info only")
    info.publication_release["_studio"]["characters"].append("info only")
    assert entity.document["work"]["tags"] == ["Fantasy"]
    assert entity.publication_release["_studio"]["characters"] == ["original"]
    assert persistence.studio_draft_entity_to_info(None) is None


def test_statistics_conversion_retains_exact_currency_strings_and_day_values():
    values = {
        "active_users": 2,
        "succeeded": 3,
        "failed": 4,
        "cancelled": 5,
        "stale": 6,
        "messages": 7,
        "conversations": 8,
        "transitions": 9,
        "input_tokens": 10,
        "output_tokens": 11,
        "cost_credit": 12,
        "revenue": {
            "USD": {
                "sales": "0.1000",
                "refunds": "0.2000",
                "net": "-0.1000",
                "sale_count": 1,
                "refund_count": 2,
            },
            "KRW": {
                "sales": "10000",
                "refunds": "0",
                "net": "10000",
                "sale_count": 3,
                "refund_count": 0,
            },
        },
    }
    updated_at = datetime.now(UTC)
    row = ProductVersionDailyStats(
        product_id=uuid4(),
        product_snapshot_id=uuid4(),
        day=date(2026, 10, 27),
        updated_at=updated_at,
        **values,
    )
    metrics = persistence.statistics_values_to_metrics_info(values)
    day = persistence.statistics_row_to_day_info(row)
    assert asdict(metrics) == values
    assert asdict(day) == {**values, "day": row.day, "updated_at": updated_at}
    values["revenue"]["USD"]["net"] = "changed input"
    assert metrics.revenue["USD"].net == "-0.1000"
    assert day.revenue["USD"].net == "-0.1000"


def test_published_view_keeps_nullable_start_title_and_snapshot_profile():
    product_id, snapshot_id = uuid4(), uuid4()
    now = datetime.now(UTC)
    product = types.ProductStateInfo(
        id=product_id,
        title="Unpublished edit",
        description="Draft",
        opening_message=None,
        visibility="private",
        status="draft",
        created_at=now,
        updated_at=now,
        owner_id=uuid4(),
        default_model_id=None,
        reasoning_effort=None,
        replacement_policy={},
        latest_snapshot_id=snapshot_id,
    )
    snapshot = types.ProductSnapshotInfo(
        snapshot_id,
        product_id,
        2,
        {"title": "Published", "description": None},
        None,
        None,
    )
    start = types.SnapshotStartInfo(uuid4(), uuid4(), None, "Opening", 0)
    composition = types.SnapshotCompositionInfo([], [], [], [start])
    view = persistence.published_product_infos_to_view(
        product, snapshot, composition, None
    )
    assert view.title == "Published" and view.description is None
    assert view.start_options == [types.StartOptionInfo(start.id, None)]
    assert view.start_options[0].id != start.source_entry_id
    assert view.model_notice is None
