# 릴리스 목록은 after_version 초과, through_version 이하를 버전순 반환한다.
# 노트가 없는 버전도 outer join으로 남겨 서비스가 전환 가능 여부를 판단하게 한다.
from datetime import datetime
from typing import TypeAlias, cast
from uuid import UUID

from sqlalchemy import Row, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.product_release import ProductReleaseNote, ProductReleaseNoteRevision
from app.db.models.snapshot.product import (
    ProductSnapshot,
)

ReleaseRow: TypeAlias = Row[tuple[ProductSnapshot, ProductReleaseNote | None]]


async def get_release_note(
    session: AsyncSession, snapshot_id: UUID, *, lock: bool = False
) -> ProductReleaseNote | None:
    return await session.get(ProductReleaseNote, snapshot_id, with_for_update=lock)


async def create_release_note(
    session: AsyncSession,
    snapshot_id: UUID,
    summary: str,
    body: str,
    kind: str,
    policy: str,
) -> None:
    session.add(
        ProductReleaseNote(
            product_snapshot_id=snapshot_id,
            summary=summary,
            body=body,
            change_kind=kind,
            update_policy=policy,
        )
    )
    await session.flush()


async def correct_release_note(
    session: AsyncSession,
    snapshot_id: UUID,
    owner_id: UUID,
    summary: str,
    body: str,
    corrected_at: datetime,
) -> ProductReleaseNote:
    note = await session.get(ProductReleaseNote, snapshot_id, with_for_update=True)
    # The caller checked and locked this note in the same transaction.
    assert note is not None, "Locked release note disappeared."
    session.add(
        ProductReleaseNoteRevision(
            product_snapshot_id=snapshot_id,
            editor_id=owner_id,
            previous_summary=note.summary,
            previous_body=note.body,
        )
    )
    note.summary, note.body, note.corrected_at = summary, body, corrected_at
    await session.flush()
    return note


async def list_product_release_rows(
    session: AsyncSession,
    product_id: UUID,
    after_version: int,
    through_version: int | None = None,
) -> list[ReleaseRow]:
    stmt = (
        select(ProductSnapshot, ProductReleaseNote)
        .outerjoin(
            ProductReleaseNote,
            ProductReleaseNote.product_snapshot_id == ProductSnapshot.id,
        )
        .where(
            ProductSnapshot.product_id == product_id,
            ProductSnapshot.version > after_version,
        )
        .order_by(ProductSnapshot.version)
    )
    if through_version is not None:
        stmt = stmt.where(ProductSnapshot.version <= through_version)
    # SQLAlchemy retains a non-null entity annotation across OUTER JOIN. SQL
    # actually returns None when the release note is absent; preserve the Row.
    return cast(list[ReleaseRow], list(await session.execute(stmt)))
