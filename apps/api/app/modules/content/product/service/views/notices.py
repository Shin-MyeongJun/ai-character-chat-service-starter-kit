# 공개 상품 안내·대화 업데이트·소유자 버전 가용성 정보를 모델 종료 안내와 합친다.
# 안내 조회는 만료 버전도 표현하며, 실제 사용 가능 여부는 시작/생성 단계에서 검사한다.
from app.modules.chatting.conversation import types as ConversationTypes
from app.modules.chatting.conversation.service import get_owned_conversation
from app.modules.content.product import types as Types
from app.modules.content.product.mapper import persistence as PersistenceMapper
from app.modules.content.product.service import query as QueryService
from app.modules.llm import types as LlmTypes
from app.modules.llm.service.replacement import execution_notice


async def get_published_product(
    session, command: Types.PublishedProductCommand
) -> Types.PublishedProductView:
    product_id = command.product_id
    user_id = command.user_id
    product = await QueryService.get_accessible_product(
        session,
        Types.GetAccessibleProductCommand(product_id=product_id, user_id=user_id),
    )
    if product.latest_snapshot_id is None:
        raise LookupError("Published product not found.")
    snapshot = await QueryService.get_product_snapshot(
        session, Types.ProductSnapshotCommand(product.latest_snapshot_id)
    )
    composition = await QueryService.get_snapshot_composition(
        session, Types.ProductSnapshotCommand(snapshot.id)
    )
    notice = await execution_notice(
        session, LlmTypes.ExecutionNoticeCommand(snapshot=snapshot)
    )
    return PersistenceMapper.published_product_infos_to_view(
        product, snapshot, composition, notice
    )


async def get_pending_updates(
    session, command: Types.PendingUpdatesCommand
) -> Types.PendingUpdatesView:
    conversation_id = command.conversation_id
    user_id = command.user_id
    conversation = await get_owned_conversation(
        session,
        ConversationTypes.OwnedConversationCommand(
            conversation_id=conversation_id, user_id=user_id
        ),
    )
    if conversation.product_snapshot_id is None:
        raise ValueError("Legacy conversation requires verified version mapping.")
    current = await QueryService.get_product_snapshot(
        session, Types.ProductSnapshotCommand(conversation.product_snapshot_id)
    )
    product = await QueryService.get_product_state(
        session, Types.GetProductStateCommand(product_id=conversation.product_id)
    )
    releases = await QueryService.list_product_releases(
        session,
        Types.ListProductReleasesCommand(
            product_id=conversation.product_id, after_version=current.version
        ),
    )
    notice = await execution_notice(
        session, LlmTypes.ExecutionNoticeCommand(snapshot=current)
    )
    return PersistenceMapper.pending_updates_infos_to_view(
        current, product, releases, notice
    )


async def get_version_availability(
    session, command: Types.VersionAvailabilityCommand
) -> Types.VersionAvailabilityView:
    product_id = command.product_id
    snapshot_id = command.snapshot_id
    owner_id = command.owner_id
    await QueryService.get_owned_product(
        session, Types.OwnedProductCommand(product_id, owner_id)
    )
    snapshot = await QueryService.get_product_snapshot(
        session, Types.ProductSnapshotCommand(snapshot_id)
    )
    if snapshot.product_id != product_id:
        raise LookupError("Version not found.")
    notice = await execution_notice(
        session, LlmTypes.ExecutionNoticeCommand(snapshot=snapshot)
    )
    return Types.VersionAvailabilityView(
        snapshot.id, snapshot.expires_at, snapshot.expiry_reason, notice
    )
