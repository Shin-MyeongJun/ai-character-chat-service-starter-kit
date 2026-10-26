"""Read-only owner totals, each counted by its owning module."""

from dataclasses import dataclass
from uuid import UUID

from app.modules.chatting.conversation import types as ConversationTypes
from app.modules.chatting.conversation.service.query import count_owned_conversations
from app.modules.content.product import types as ProductTypes
from app.modules.content.product.service.query import count_products


@dataclass(frozen=True, slots=True)
class GetAccountCountsCommand:
    owner_id: UUID


async def get_account_counts(session, command: GetAccountCountsCommand) -> dict[str, int]:
    """Compose exact owner counts via public services in the caller's read transaction."""
    conversations = await count_owned_conversations(session, ConversationTypes.ListOwnedConversationsCommand(command.owner_id))
    products = await count_products(session, ProductTypes.ListProductsCommand(owner_id=command.owner_id))
    return {"conversations": conversations, "products": products}
