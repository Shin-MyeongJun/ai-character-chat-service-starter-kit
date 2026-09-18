# 상품 초안은 소유자 기준으로 관리하고 발행 이력이 있으면 삭제를 거절한다.
# 만료/상태 정책 변경은 identity.require_admin으로 DB 사용자 역할·상태를 검사한다.
"Commands own transactions; owner_id must come from trusted authentication."

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.transaction import use_case_transaction
from app.modules.content.product import repository as Repository
from app.modules.content.product import types as Types
from app.modules.content.product.mapper import persistence as PersistenceMapper
from app.modules.content.product.mapper.persistence import product_entity_to_info
from app.modules.content.product.service import query as QueryService
from app.modules.identity import types as IdentityTypes
from app.modules.identity.service import query as IdentityQueryService


def validate_profile(value: Types.ProductProfileCommand):
    if not value.title.strip() or len(value.title) > 200:
        raise ValueError("Title must contain 1–200 characters.")
    if value.visibility not in ("private", "public", "unlisted"):
        raise ValueError("Invalid visibility.")
    for field in (value.description, value.opening_message):
        if field is not None and len(field) > 20000:
            raise ValueError("Text exceeds 20000 characters.")


async def create_product(
    session: AsyncSession, command: Types.CreateProductCommand
) -> Types.ProductInfo:
    owner_id = command.owner_id
    value = command.value
    validate_profile(value)
    async with use_case_transaction(session):
        row = await Repository.create_product(session, owner_id, value)
        return product_entity_to_info(row)


async def update_product(
    session: AsyncSession, command: Types.UpdateProductCommand
) -> Types.ProductInfo:
    product_id = command.product_id
    owner_id = command.owner_id
    value = command.value
    validate_profile(value)
    async with use_case_transaction(session):
        await QueryService.get_owned_product(
            session, Types.OwnedProductCommand(product_id, owner_id, lock=True)
        )
        row = await Repository.update_product(session, product_id, owner_id, value)
        return product_entity_to_info(row)


async def delete_product(
    session: AsyncSession, command: Types.DeleteProductCommand
) -> None:
    product_id = command.product_id
    owner_id = command.owner_id
    async with use_case_transaction(session):
        await QueryService.get_owned_product(
            session, Types.OwnedProductCommand(product_id, owner_id, lock=True)
        )
        if await Repository.has_product_snapshot(session, product_id):
            raise ValueError("Published products must be retired, not deleted.")
        await Repository.delete_product(session, product_id, owner_id)


async def change_snapshot_expiry(
    session, command: Types.ChangeSnapshotExpiryCommand
) -> Types.ProductSnapshotInfo:
    if not command.reason.strip() or len(command.reason) > 2000:
        raise ValueError("Reason must contain 1–2000 characters.")
    if command.expires_at is not None and (
        command.expires_at.tzinfo is None or command.expires_at.utcoffset() is None
    ):
        raise ValueError("Expiry must include a timezone.")
    async with use_case_transaction(session):
        await IdentityQueryService.require_admin(
            session, IdentityTypes.GetUserCommand(command.actor_id)
        )
        await QueryService.get_product_snapshot(
            session, Types.ProductSnapshotCommand(command.snapshot_id, lock=True)
        )
        await Repository.set_product_snapshot_expiry(
            session,
            command.snapshot_id,
            command.actor_id,
            command.expires_at,
            command.reason,
        )
        return await QueryService.get_product_snapshot(
            session, Types.ProductSnapshotCommand(command.snapshot_id)
        )


async def change_product_status(
    session, command: Types.ChangeProductStatusCommand
) -> Types.ProductInfo:
    if command.status not in ("approved", "rejected", "draft"):
        raise ValueError("Invalid product status.")
    async with use_case_transaction(session):
        await IdentityQueryService.require_admin(
            session, IdentityTypes.GetUserCommand(command.actor_id)
        )
        row = await Repository.get_product(session, command.product_id, lock=True)
        info = PersistenceMapper.product_entity_to_state_info(row)
        if info is None:
            raise LookupError("Product not found.")
        await Repository.set_product_status(session, command.product_id, command.status)
        row = await Repository.get_product(session, command.product_id)
        return PersistenceMapper.product_entity_to_info(row)
