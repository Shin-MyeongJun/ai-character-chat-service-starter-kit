# 고정 상품 스냅샷·활성 로어·실행 모델을 조합한다. 모델 대체 이력을 저장할 수 있어 쓰기 트랜잭션을 사용한다.
# activation_text만 로어 활성화에 사용하며 메시지 이력을 직접 조회하지 않는다.
from app.db.transaction import use_case_transaction
from app.modules.chatting.conversation import types as Types
from app.modules.chatting.conversation.mapper import persistence as PersistenceMapper
from app.modules.chatting.conversation.service.query import get_owned_conversation
from app.modules.content.lorebook import types as LorebookTypes
from app.modules.content.lorebook.service import query as LorebookQueryService
from app.modules.content.product import types as ProductTypes
from app.modules.content.product.service import query as ProductQueryService
from app.modules.content.product.service import views as ProductViewsService
from app.modules.llm import types as LlmTypes
from app.modules.llm.service.replacement import resolve_execution


async def prepare_runtime_context(
    session, command: Types.PrepareRuntimeContextCommand
) -> Types.ConversationRuntimeView:
    async with use_case_transaction(session):
        conversation_id = command.conversation_id
        user_id = command.user_id
        conversation = await get_owned_conversation(
            session,
            Types.OwnedConversationCommand(
                conversation_id=conversation_id, user_id=user_id
            ),
        )
        if conversation.product_snapshot_id is None:
            raise ValueError("Legacy conversation requires verified version mapping.")
        snapshot = await ProductQueryService.ensure_snapshot_available(
            session,
            ProductTypes.ProductSnapshotCommand(conversation.product_snapshot_id),
        )
        runtime = await ProductViewsService.get_snapshot_runtime(
            session, ProductTypes.ProductSnapshotCommand(snapshot.id)
        )
        execution = await resolve_execution(
            session, LlmTypes.ResolveExecutionCommand(snapshot_id=snapshot.id)
        )
        active_entries = {
            sid: LorebookQueryService.activate_snapshot_entries(
                LorebookTypes.ActivateSnapshotEntriesCommand(
                    snapshot=book, text=command.activation_text
                )
            ).entries
            for sid, book in runtime.lorebooks.items()
        }
        return PersistenceMapper.conversation_snapshot_infos_to_runtime_view(
            conversation, snapshot, runtime, execution, active_entries
        )
