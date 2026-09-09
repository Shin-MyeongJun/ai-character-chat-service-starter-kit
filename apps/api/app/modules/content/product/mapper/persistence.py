from app.modules.content.product import types
from app.modules.content.product.types import (
    ProductInfo,
    RevenueInfo,
    StatisticsDayInfo,
    StatisticsMetrics,
)


def to_info(entity):
    return ProductInfo(
        **{name: getattr(entity, name) for name in ProductInfo.__dataclass_fields__}
    )


def to_statistics_metrics(values: dict) -> StatisticsMetrics:
    return StatisticsMetrics(
        **{
            **values,
            "revenue": {
                currency: RevenueInfo(**bucket)
                for currency, bucket in values["revenue"].items()
            },
        }
    )


def to_statistics_day(row) -> StatisticsDayInfo:
    fields = {
        name: getattr(row, name) for name in StatisticsMetrics.__dataclass_fields__
    }
    fields["revenue"] = {
        currency: RevenueInfo(**bucket) for currency, bucket in row.revenue.items()
    }
    return StatisticsDayInfo(day=row.day, updated_at=row.updated_at, **fields)


def composition_to_info(characters, books, links) -> types.Composition:
    ids = {c.id: c.character_id for c in characters}
    return types.Composition(
        tuple(
            types.CharacterSelection(c.character_id, c.is_primary, c.role_name)
            for c in characters
        ),
        tuple(
            types.LorebookSelection(
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
