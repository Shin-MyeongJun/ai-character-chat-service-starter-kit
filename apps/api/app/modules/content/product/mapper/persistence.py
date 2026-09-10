from copy import deepcopy
from typing import overload

from app.db.models.product import Product
from app.db.models.snapshot.product import ProductSnapshot
from app.modules.content.product import types as Types
from app.modules.content.product.types import (
    ProductInfo,
    RevenueInfo,
    StatisticsDayInfo,
    StatisticsMetricsInfo,
)


def product_entity_to_info(entity):
    return ProductInfo(
        **{name: getattr(entity, name) for name in ProductInfo.__dataclass_fields__}
    )


def statistics_values_to_metrics_info(values: dict) -> StatisticsMetricsInfo:
    return StatisticsMetricsInfo(
        **{
            **values,
            "revenue": {
                currency: RevenueInfo(**bucket)
                for currency, bucket in values["revenue"].items()
            },
        }
    )


def statistics_row_to_day_info(row) -> StatisticsDayInfo:
    fields = {
        name: getattr(row, name) for name in StatisticsMetricsInfo.__dataclass_fields__
    }
    fields["revenue"] = {
        currency: RevenueInfo(**bucket) for currency, bucket in row.revenue.items()
    }
    return StatisticsDayInfo(day=row.day, updated_at=row.updated_at, **fields)


def composition_entities_to_info(
    characters, books, links
) -> Types.ProductCompositionInfo:
    ids = {c.id: c.character_id for c in characters}
    return Types.ProductCompositionInfo(
        tuple(
            Types.CharacterSelection(c.character_id, c.is_primary, c.role_name)
            for c in characters
        ),
        tuple(
            Types.LorebookSelection(
                b.lorebook_id,
                b.scope,
                tuple(
                    ids[t.product_character_id]
                    for t in links
                    if t.product_lorebook_id == b.id
                ),
                b.role,
                b.priority,
                b.is_required,
            )
            for b in books
        ),
    )


@overload
def product_entity_to_state_info(entity: Product) -> Types.ProductStateInfo: ...


@overload
def product_entity_to_state_info(entity: None) -> None: ...


def product_entity_to_state_info(
    entity: Product | None,
) -> Types.ProductStateInfo | None:
    if entity is None:
        return None
    return Types.ProductStateInfo(
        **{
            name: deepcopy(getattr(entity, name))
            for name in Types.ProductStateInfo.__dataclass_fields__
        }
    )


@overload
def product_snapshot_entity_to_info(
    entity: ProductSnapshot,
) -> Types.ProductSnapshotInfo: ...


@overload
def product_snapshot_entity_to_info(entity: None) -> None: ...


def product_snapshot_entity_to_info(
    entity: ProductSnapshot | None,
) -> Types.ProductSnapshotInfo | None:
    if entity is None:
        return None
    return Types.ProductSnapshotInfo(
        **{
            name: deepcopy(getattr(entity, name))
            for name in Types.ProductSnapshotInfo.__dataclass_fields__
        }
    )


def products_entities_to_info(entities) -> list[Types.ProductInfo]:
    return [product_entity_to_info(entity) for entity in entities]


def product_composition_row_to_info(row) -> Types.ProductCompositionInfo:
    return composition_entities_to_info(row.characters, row.books, row.links)


def product_start_sets_entities_to_info(entities) -> list[Types.ProductStartSetInfo]:
    return [
        Types.ProductStartSetInfo(
            **{
                name: getattr(row, name)
                for name in Types.ProductStartSetInfo.__dataclass_fields__
            }
        )
        for row in entities
    ]


def product_composition_row_to_state_info(row) -> Types.ProductCompositionStateInfo:
    return Types.ProductCompositionStateInfo(
        [
            Types.ProductCharacterLinkInfo(
                **{
                    key: getattr(c, key)
                    for key in Types.ProductCharacterLinkInfo.__dataclass_fields__
                }
            )
            for c in row.characters
        ],
        [
            Types.ProductLorebookLinkInfo(
                **{
                    key: getattr(b, key)
                    for key in Types.ProductLorebookLinkInfo.__dataclass_fields__
                }
            )
            for b in row.books
        ],
        [
            Types.ProductLorebookTargetInfo(
                t.product_character_id, t.product_lorebook_id
            )
            for t in row.links
        ],
    )


def release_note_entity_to_info(entity) -> Types.ReleaseNoteInfo | None:
    if entity is None:
        return None
    return Types.ReleaseNoteInfo(
        entity.summary, entity.body, entity.change_kind, entity.update_policy
    )


def snapshot_composition_row_to_info(row) -> Types.SnapshotCompositionInfo:
    return Types.SnapshotCompositionInfo(
        [
            Types.SnapshotCharacterInfo(
                **{
                    key: getattr(c, key)
                    for key in Types.SnapshotCharacterInfo.__dataclass_fields__
                }
            )
            for c in row.characters
        ],
        [
            Types.SnapshotLorebookInfo(
                **{
                    key: getattr(b, key)
                    for key in Types.SnapshotLorebookInfo.__dataclass_fields__
                }
            )
            for b in row.books
        ],
        [
            Types.ProductLorebookTargetInfo(
                t.product_character_id, t.product_lorebook_id
            )
            for t in row.targets
        ],
        [
            Types.SnapshotStartInfo(
                **{
                    key: getattr(s, key)
                    for key in Types.SnapshotStartInfo.__dataclass_fields__
                }
            )
            for s in row.starts
        ],
    )


def snapshot_components_infos_to_view(
    composition, characters, lorebooks
) -> Types.SnapshotRuntimeView:
    return Types.SnapshotRuntimeView(
        composition, {c.id: c for c in characters}, {b.id: b for b in lorebooks}
    )


def product_releases_rows_to_info(rows):
    return [
        (product_snapshot_entity_to_info(snapshot), release_note_entity_to_info(note))
        for snapshot, note in rows
    ]


def published_product_infos_to_view(
    product, snapshot, composition, notice
) -> Types.PublishedProductView:
    return Types.PublishedProductView(
        product.id,
        snapshot.id,
        snapshot.version,
        snapshot.snapshot_data["title"],
        snapshot.snapshot_data["description"],
        [Types.StartOptionInfo(s.id, s.title) for s in composition.starts],
        notice,
    )


def pending_updates_infos_to_view(
    current, product, releases, notice
) -> Types.PendingUpdatesView:
    return Types.PendingUpdatesView(
        current.id,
        current.expires_at,
        current.expiry_reason,
        product.latest_snapshot_id,
        [
            Types.UpdateInfo(
                s.id,
                s.version,
                n.summary,
                n.body,
                n.change_kind,
                n.update_policy,
                s.expires_at,
            )
            for s, n in releases
            if n is not None
        ],
        notice,
    )


def statistics_work_entity_to_info(entity) -> Types.StatisticsWorkInfo | None:
    if entity is None:
        return None
    return Types.StatisticsWorkInfo(entity.product_id, entity.day)
