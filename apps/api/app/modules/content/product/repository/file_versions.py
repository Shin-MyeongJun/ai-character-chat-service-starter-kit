from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, exists, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.product_file_version import ProductFileReference, ProductFileVersion
from app.modules.content.product import types as Types


async def get_file_version(
    session: AsyncSession, command: Types.GetProductFileVersionCommand, *, lock: bool
) -> ProductFileVersion | None:
    statement = select(ProductFileVersion).where(
        ProductFileVersion.id == command.file_version_id,
        ProductFileVersion.product_id == command.product_id,
    )
    if lock:
        statement = statement.with_for_update().execution_options(
            populate_existing=True
        )
    entity: ProductFileVersion | None = await session.scalar(statement)
    return entity


async def get_file_request(
    session: AsyncSession, product_id: UUID, owner_id: UUID, request_id: UUID
) -> ProductFileVersion | None:
    entity: ProductFileVersion | None = await session.scalar(
        select(ProductFileVersion).where(
            ProductFileVersion.product_id == product_id,
            ProductFileVersion.owner_id == owner_id,
            ProductFileVersion.request_id == request_id,
        )
    )
    return entity


async def insert_file_version(
    session: AsyncSession, entity: ProductFileVersion
) -> ProductFileVersion:
    session.add(entity)
    await session.flush()
    return entity


async def set_file_state(
    session: AsyncSession, file_version_id: UUID, state: Types.ProductFileVersionState
) -> None:
    await session.execute(
        update(ProductFileVersion)
        .where(ProductFileVersion.id == file_version_id)
        .values(state=state)
    )


async def set_file_retention(
    session: AsyncSession,
    file_version_id: UUID,
    *,
    awaiting_attachment: bool,
    unreferenced_since: datetime | None,
) -> None:
    await session.execute(
        update(ProductFileVersion)
        .where(ProductFileVersion.id == file_version_id)
        .values(
            awaiting_attachment=awaiting_attachment,
            unreferenced_since=unreferenced_since,
        )
    )


async def has_file_references(session: AsyncSession, file_version_id: UUID) -> bool:
    return bool(
        await session.scalar(
            select(
                exists().where(ProductFileReference.file_version_id == file_version_id)
            )
        )
    )


async def has_file_reference(
    session: AsyncSession, command: Types.ProductFileReferenceCommand
) -> bool:
    return bool(
        await session.scalar(
            select(
                exists().where(
                    ProductFileReference.file_version_id == command.file_version_id,
                    ProductFileReference.kind == command.kind,
                    ProductFileReference.reference_id == command.reference_id,
                )
            )
        )
    )


async def insert_file_reference(
    session: AsyncSession, command: Types.ProductFileReferenceCommand
) -> None:
    session.add(
        ProductFileReference(
            file_version_id=command.file_version_id,
            kind=command.kind,
            reference_id=command.reference_id,
        )
    )
    await session.flush()


async def delete_file_reference(
    session: AsyncSession, command: Types.ProductFileReferenceCommand
) -> None:
    await session.execute(
        delete(ProductFileReference).where(
            ProductFileReference.file_version_id == command.file_version_id,
            ProductFileReference.kind == command.kind,
            ProductFileReference.reference_id == command.reference_id,
        )
    )
