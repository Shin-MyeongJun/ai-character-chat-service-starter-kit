# 초안·스냅샷을 값으로 변환하며 JSON을 deepcopy한다. 업데이트 안내에서는 노트 없는 릴리스를 제외한다.
from collections.abc import Iterable, Sequence
from copy import deepcopy
from typing import Literal, cast, overload

from sqlalchemy import Row

from app.db.models.product import (
    Product,
    ProductCharacter,
    ProductLorebook,
    ProductLorebookCharacter,
    ProductStartSet,
    ProductStudioDraft,
)
from app.db.models.product_release import ProductReleaseNote
from app.db.models.product_statistics import (
    ProductDailyStats,
    ProductStatsDirtyDay,
    ProductVersionDailyStats,
)
from app.db.models.snapshot.product import ProductSnapshot
from app.modules.content.character import types as CharacterTypes
from app.modules.content.lorebook import types as LorebookTypes
from app.modules.content.product import types as Types
from app.modules.content.product.repository.composition import ProductCompositionRow
from app.modules.content.product.repository.core import CatalogRow
from app.modules.content.product.repository.publication import SnapshotCompositionRow
from app.modules.content.product.types import (
    ProductInfo,
    RevenueInfo,
    StatisticsDayInfo,
    StatisticsMetricsInfo,
)
from app.modules.llm import types as LlmTypes


@overload
def product_entity_to_info(entity: Product) -> Types.ProductInfo: ...


@overload
def product_entity_to_info(entity: None) -> None: ...


def product_entity_to_info(entity: Product | None) -> Types.ProductInfo | None:
    """Expose publication existence separately from moderation status."""
    if entity is None:
        return None
    return ProductInfo(
        id=entity.id,
        title=entity.title,
        description=entity.description,
        opening_message=entity.opening_message,
        visibility=entity.visibility,
        status=entity.status,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
        has_publication=entity.latest_snapshot_id is not None,
    )


def catalog_entities_to_page_info(
    rows: Sequence[CatalogRow | tuple[Product, ProductSnapshot]], limit: int
) -> Types.CatalogPageInfo:
    """Read the published profile shape shared by publication and public detail."""
    selected = rows[:limit]
    items = tuple(
        Types.CatalogProductInfo(
            id=product.id,
            title=snapshot.snapshot_data["title"],
            description=snapshot.snapshot_data.get("description"),
            snapshot_id=snapshot.id,
            created_at=product.created_at,
        )
        for product, snapshot in selected
    )
    last = selected[-1][0] if len(rows) > limit else None
    return Types.CatalogPageInfo(
        items=items,
        next_cursor_created_at=last.created_at if last else None,
        next_cursor_id=last.id if last else None,
    )


@overload
def studio_draft_entity_to_info(
    entity: ProductStudioDraft,
) -> Types.StudioDraftInfo: ...


@overload
def studio_draft_entity_to_info(entity: None) -> None: ...


def studio_draft_entity_to_info(
    entity: ProductStudioDraft | None,
) -> Types.StudioDraftInfo | None:
    if entity is None:
        return None
    return Types.StudioDraftInfo(
        product_id=entity.product_id,
        revision=entity.revision,
        document=deepcopy(entity.document),
        updated_at=entity.updated_at,
        content_digest=entity.content_digest,
        publication_digest=entity.publication_digest,
        publication_release=deepcopy(entity.publication_release),
    )


def statistics_values_to_metrics_info(
    values: Types.StatisticsMetricsValues,
) -> StatisticsMetricsInfo:
    return StatisticsMetricsInfo(
        active_users=values["active_users"],
        succeeded=values["succeeded"],
        failed=values["failed"],
        cancelled=values["cancelled"],
        stale=values["stale"],
        messages=values["messages"],
        conversations=values["conversations"],
        transitions=values["transitions"],
        input_tokens=values["input_tokens"],
        output_tokens=values["output_tokens"],
        cost_credit=values["cost_credit"],
        revenue={
            currency: RevenueInfo(**bucket)
            for currency, bucket in values["revenue"].items()
        },
    )


def statistics_row_to_day_info(
    row: ProductDailyStats | ProductVersionDailyStats,
) -> StatisticsDayInfo:
    return StatisticsDayInfo(
        day=row.day,
        updated_at=row.updated_at,
        active_users=row.active_users,
        succeeded=row.succeeded,
        failed=row.failed,
        cancelled=row.cancelled,
        stale=row.stale,
        messages=row.messages,
        conversations=row.conversations,
        transitions=row.transitions,
        input_tokens=row.input_tokens,
        output_tokens=row.output_tokens,
        cost_credit=row.cost_credit,
        revenue={
            currency: RevenueInfo(**bucket) for currency, bucket in row.revenue.items()
        },
    )


def composition_entities_to_info(
    characters: Sequence[ProductCharacter],
    books: Sequence[ProductLorebook],
    links: Sequence[ProductLorebookCharacter],
) -> Types.ProductCompositionInfo:
    character_ids_by_link_id = {c.id: c.character_id for c in characters}
    # ProductLorebook CHECK constraints restrict scope and role to these literals.
    return Types.ProductCompositionInfo(
        tuple(
            Types.CharacterSelection(c.character_id, c.is_primary, c.role_name)
            for c in characters
        ),
        tuple(
            Types.LorebookSelection(
                b.lorebook_id,
                cast(Literal["all", "selected"], b.scope),
                tuple(
                    character_ids_by_link_id[t.product_character_id]
                    for t in links
                    if t.product_lorebook_id == b.id
                ),
                cast(Literal["main", "detail", "rule", "optional"], b.role),
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
    """Detach mutable product state and its independent publication indicator."""
    if entity is None:
        return None
    return Types.ProductStateInfo(
        id=entity.id,
        title=entity.title,
        description=entity.description,
        opening_message=entity.opening_message,
        visibility=entity.visibility,
        status=entity.status,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
        has_publication=entity.latest_snapshot_id is not None,
        owner_id=entity.owner_id,
        default_model_id=entity.default_model_id,
        reasoning_effort=entity.reasoning_effort,
        replacement_policy=deepcopy(entity.replacement_policy),
        latest_snapshot_id=entity.latest_snapshot_id,
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
        id=entity.id,
        product_id=entity.product_id,
        version=entity.version,
        # create/finish_product_snapshot write the declared profile keys. The
        # shared JSONB mixin cannot express domain keys; keep all extension fields
        # and the existing runtime errors for malformed stored data.
        snapshot_data=cast(Types.ProductSnapshotData, deepcopy(entity.snapshot_data)),
        expires_at=entity.expires_at,
        expiry_reason=entity.expiry_reason,
    )


def products_entities_to_info(entities: Iterable[Product]) -> list[Types.ProductInfo]:
    return [product_entity_to_info(entity) for entity in entities]


def product_composition_row_to_info(
    row: ProductCompositionRow,
) -> Types.ProductCompositionInfo:
    return composition_entities_to_info(row.characters, row.books, row.links)


def product_start_sets_entities_to_info(
    entities: Iterable[ProductStartSet],
) -> list[Types.ProductStartSetInfo]:
    return [
        Types.ProductStartSetInfo(
            id=entity.id,
            product_id=entity.product_id,
            lorebook_id=entity.lorebook_id,
            entry_id=entity.entry_id,
            sort_order=entity.sort_order,
        )
        for entity in entities
    ]


def product_composition_row_to_state_info(
    row: ProductCompositionRow,
) -> Types.ProductCompositionStateInfo:
    return Types.ProductCompositionStateInfo(
        [
            Types.ProductCharacterLinkInfo(
                id=entity.id,
                character_id=entity.character_id,
                role_order=entity.role_order,
                role_name=entity.role_name,
                is_primary=entity.is_primary,
            )
            for entity in row.characters
        ],
        [
            Types.ProductLorebookLinkInfo(
                id=entity.id,
                lorebook_id=entity.lorebook_id,
                role=entity.role,
                priority=entity.priority,
                is_required=entity.is_required,
                scope=entity.scope,
            )
            for entity in row.books
        ],
        [
            Types.ProductLorebookTargetInfo(
                entity.product_character_id, entity.product_lorebook_id
            )
            for entity in row.links
        ],
    )


def release_note_entity_to_info(
    entity: ProductReleaseNote | None,
) -> Types.ReleaseNoteInfo | None:
    if entity is None:
        return None
    return Types.ReleaseNoteInfo(
        entity.summary, entity.body, entity.change_kind, entity.update_policy
    )


def snapshot_composition_row_to_info(
    row: SnapshotCompositionRow,
) -> Types.SnapshotCompositionInfo:
    return Types.SnapshotCompositionInfo(
        [
            Types.SnapshotCharacterInfo(
                id=entity.id,
                character_snapshot_id=entity.character_snapshot_id,
                role_order=entity.role_order,
                role_name=entity.role_name,
                is_primary=entity.is_primary,
            )
            for entity in row.characters
        ],
        [
            Types.SnapshotLorebookInfo(
                id=entity.id,
                lorebook_snapshot_id=entity.lorebook_snapshot_id,
                role=entity.role,
                priority=entity.priority,
                is_required=entity.is_required,
                scope=entity.scope,
            )
            for entity in row.books
        ],
        [
            Types.ProductLorebookTargetInfo(
                entity.product_character_id, entity.product_lorebook_id
            )
            for entity in row.targets
        ],
        [
            Types.SnapshotStartInfo(
                id=entity.id,
                source_entry_id=entity.source_entry_id,
                title=entity.title,
                content=entity.content,
                sort_order=entity.sort_order,
            )
            for entity in row.starts
        ],
    )


def snapshot_components_infos_to_view(
    composition: Types.SnapshotCompositionInfo,
    characters: Iterable[CharacterTypes.CharacterSnapshotInfo],
    lorebooks: Iterable[LorebookTypes.LorebookSnapshotInfo],
) -> Types.SnapshotRuntimeView:
    return Types.SnapshotRuntimeView(
        composition, {c.id: c for c in characters}, {b.id: b for b in lorebooks}
    )


def product_releases_rows_to_info(
    rows: Iterable[
        Row[tuple[ProductSnapshot, ProductReleaseNote | None]]
        | tuple[ProductSnapshot, ProductReleaseNote | None]
    ],
) -> list[tuple[Types.ProductSnapshotInfo, Types.ReleaseNoteInfo | None]]:
    return [
        (product_snapshot_entity_to_info(snapshot), release_note_entity_to_info(note))
        for snapshot, note in rows
    ]


def published_product_infos_to_view(
    product: Types.ProductStateInfo,
    snapshot: Types.ProductSnapshotInfo,
    composition: Types.SnapshotCompositionInfo,
    notice: LlmTypes.ModelNoticeView | None,
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
    current: Types.ProductSnapshotInfo,
    product: Types.ProductStateInfo,
    releases: Iterable[tuple[Types.ProductSnapshotInfo, Types.ReleaseNoteInfo | None]],
    notice: LlmTypes.ModelNoticeView | None,
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


def statistics_work_entity_to_info(
    entity: ProductStatsDirtyDay | None,
) -> Types.StatisticsWorkInfo | None:
    if entity is None:
        return None
    return Types.StatisticsWorkInfo(entity.product_id, entity.day)
