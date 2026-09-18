# 상품 만료·검수 상태 변경을 product 공개 Command로 위임한다. 관리자 검사는 해당 product 서비스에서 수행한다.
from app.modules.content.product import types as ProductTypes
from app.modules.content.product.service import command as ProductCommandService
from app.modules.governance.admin import types as Types
from app.modules.governance.admin.types import ExpiryChangedInfo


async def set_expiry(session, command: Types.SetExpiryCommand) -> ExpiryChangedInfo:
    snapshot_id = command.snapshot_id
    actor_id = command.actor_id
    expires_at = command.expires_at
    reason = command.reason
    info = await ProductCommandService.change_snapshot_expiry(
        session,
        ProductTypes.ChangeSnapshotExpiryCommand(
            snapshot_id, actor_id, expires_at, reason
        ),
    )
    return ExpiryChangedInfo(info.id, info.expires_at, command.reason)


async def moderate_product(
    session, command: Types.ModerateProductCommand
) -> Types.ModeratedProductInfo:
    product_id = command.product_id
    actor_id = command.actor_id
    status = command.status
    info = await ProductCommandService.change_product_status(
        session, ProductTypes.ChangeProductStatusCommand(product_id, actor_id, status)
    )
    return Types.ModeratedProductInfo(info.id, info.status)
