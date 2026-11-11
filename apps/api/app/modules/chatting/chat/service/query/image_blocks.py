from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.chatting.chat import repository as Repository
from app.modules.chatting.chat import types as Types
from app.modules.chatting.chat.mapper import persistence as PersistenceMapper
from app.modules.chatting.conversation import types as ConversationTypes
from app.modules.chatting.conversation.service import get_owned_conversation
from app.modules.content.product import types as ProductTypes


async def authorize_message_image_block(
    session: AsyncSession, command: Types.ReadMessageBlockCommand
) -> ProductTypes.ProductFileReferenceCommand:
    conversation = await get_owned_conversation(
        session,
        ConversationTypes.OwnedConversationCommand(
            conversation_id=command.conversation_id, user_id=command.user_id
        ),
    )
    message = PersistenceMapper.message_entity_to_info(
        await Repository.get_message(
            session, command.conversation_id, command.message_id
        )
    )
    if (
        message is None
        or message.revision != command.revision
        or message.product_snapshot_id is None
        or message.content_blocks is None
        or not 0 <= command.block_index < len(message.content_blocks)
    ):
        raise LookupError("Image occurrence not found.")
    block = message.content_blocks[command.block_index]
    if not isinstance(block, ProductTypes.ImageContentBlockInfo):
        raise LookupError("Image occurrence not found.")
    # Message/generation snapshot FKs retain this immutable publication; expiry
    # affects new execution, not an owner's surviving message occurrence.
    return ProductTypes.ProductFileReferenceCommand(
        product_id=conversation.product_id,
        file_version_id=block.file_version_id,
        kind="snapshot",
        reference_id=message.product_snapshot_id,
    )
