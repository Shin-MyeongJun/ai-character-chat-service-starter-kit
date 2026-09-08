"""Internal atomic publication builder; public command adds required release notes."""

import hashlib
import json
from uuid import uuid4

from sqlalchemy import select

from app.db.models.character import Character
from app.db.models.lorebook import Lorebook, LorebookEntry
from app.db.models.model_routing import Provider
from app.db.models.product import ProductLorebook, ProductLorebookCharacter
from app.db.models.snapshot.product import (
    ProductSnapshot,
    ProductSnapshotCharacter,
    ProductSnapshotLorebook,
    ProductSnapshotLorebookCharacter,
    ProductSnapshotStartSet,
)
from app.modules.content.product import repository
from app.modules.content.product.service import settings, snapshots


async def build_publication(session, *, product_id, owner_id):
    """Caller must own a transaction. Product/source locks serialize all publication reads."""
    if not session.in_transaction():
        raise RuntimeError("Publication requires a caller transaction.")
    product = await repository.owned(session, product_id, owner_id, lock=True)
    # Lock all content parents in a deterministic order before reading children.
    from app.db.models.product import ProductCharacter

    char_links = list(
        await session.scalars(
            select(ProductCharacter)
            .where(ProductCharacter.product_id == product_id)
            .order_by(ProductCharacter.role_order, ProductCharacter.id)
        )
    )
    book_links = list(
        await session.scalars(
            select(ProductLorebook)
            .where(ProductLorebook.product_id == product_id)
            .order_by(ProductLorebook.id)
        )
    )
    sources = []
    for cls, ids in (
        (Character, [c.character_id for c in char_links]),
        (Lorebook, [b.lorebook_id for b in book_links]),
    ):
        rows = list(
            await session.scalars(
                select(cls)
                .where(cls.id.in_(ids), cls.owner_id == owner_id)
                .order_by(cls.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )
        if len(rows) != len(ids):
            raise LookupError("Owned component not found.")
        sources.append({r.id: r for r in rows})
    _, starts = await settings.validate_publication(session, product)
    model = await settings.validate_model(
        session, product.default_model_id, product.reasoning_effort
    )
    provider = await session.get(Provider, model.provider_id)
    targets = list(
        await session.scalars(
            select(ProductLorebookCharacter).where(
                ProductLorebookCharacter.product_id == product_id
            )
        )
    )
    for b in book_links:
        count = sum(t.product_lorebook_id == b.id for t in targets)
        if (b.scope == "selected" and count == 0) or (b.scope == "all" and count):
            raise ValueError("Invalid lorebook targets.")
    data = {
        "title": product.title,
        "description": product.description,
        "opening_message": product.opening_message,
        "model": {
            "id": str(model.id),
            "provider_id": str(model.provider_id),
            "provider": provider.name,
            "name": model.model_name,
            "family": model.capabilities.get("model_family"),
            "reasoning_effort": product.reasoning_effort,
        },
        "replacement_policy": product.replacement_policy,
    }
    snapshot = ProductSnapshot(
        id=uuid4(),
        product_id=product_id,
        version=await snapshots.next_version(
            session, ProductSnapshot, ProductSnapshot.product_id, product_id
        ),
        snapshot_schema_version=2,
        snapshot_data=data,
    )
    session.add(snapshot)
    await session.flush()
    chars, books, canonical_chars, canonical_books = {}, {}, [], []
    for c in char_links:
        component = await snapshots.freeze_character(
            session, sources[0][c.character_id]
        )
        link = ProductSnapshotCharacter(
            id=uuid4(),
            product_snapshot_id=snapshot.id,
            character_snapshot_id=component.id,
            role_order=c.role_order,
            role_name=c.role_name,
            is_primary=c.is_primary,
        )
        session.add(link)
        chars[c.id] = link.id
        canonical_chars.append(
            {
                "source_id": str(c.character_id),
                "data": component.snapshot_data,
                "order": c.role_order,
                "role": c.role_name,
                "primary": c.is_primary,
            }
        )
    source_ids = {c.id: str(c.character_id) for c in char_links}
    for b in book_links:
        component = await snapshots.freeze_lorebook(session, sources[1][b.lorebook_id])
        link = ProductSnapshotLorebook(
            id=uuid4(),
            product_snapshot_id=snapshot.id,
            lorebook_snapshot_id=component.id,
            role=b.role,
            priority=b.priority,
            is_required=b.is_required,
            scope=b.scope,
        )
        session.add(link)
        books[b.id] = link.id
        canonical_books.append(
            {
                "source_id": str(b.lorebook_id),
                "data": component.snapshot_data,
                "role": b.role,
                "priority": b.priority,
                "required": b.is_required,
                "scope": b.scope,
                "targets": sorted(
                    source_ids[t.product_character_id]
                    for t in targets
                    if t.product_lorebook_id == b.id
                ),
            }
        )
    await session.flush()
    for t in targets:
        session.add(
            ProductSnapshotLorebookCharacter(
                product_snapshot_id=snapshot.id,
                product_character_id=chars[t.product_character_id],
                product_lorebook_id=books[t.product_lorebook_id],
            )
        )
    book_by_source = {b.lorebook_id: b.id for b in book_links}
    for start in starts:
        entry = await session.get(LorebookEntry, start.entry_id)
        session.add(
            ProductSnapshotStartSet(
                product_snapshot_id=snapshot.id,
                product_lorebook_id=books[book_by_source[start.lorebook_id]],
                source_entry_id=entry.id,
                title=entry.title,
                content=entry.content,
                sort_order=start.sort_order,
            )
        )
    canonical = {
        "product": data,
        "characters": canonical_chars,
        "lorebooks": sorted(canonical_books, key=lambda b: b["source_id"]),
        "starts": [str(s.entry_id) for s in sorted(starts, key=lambda s: s.sort_order)],
    }
    snapshot.snapshot_data = {
        **data,
        "content_digest": hashlib.sha256(
            json.dumps(canonical, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest(),
    }
    await session.flush()
    product.latest_snapshot_id = snapshot.id
    await session.flush()
    return snapshot
