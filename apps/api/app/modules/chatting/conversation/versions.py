from datetime import UTC, datetime

from sqlalchemy import delete, select

from app.db.models.chat import ConversationCharacter, ConversationVersionChange
from app.db.models.product_release import ProductReleaseNote
from app.db.models.snapshot.character import CharacterSnapshot
from app.db.models.snapshot.product import ProductSnapshot, ProductSnapshotCharacter
from app.db.product_stats_queue import mark_dirty
from app.modules.chatting.conversation.service import owned_conversation
from app.modules.chatting.conversation.types import VersionSwitched
from app.modules.governance.admin.product_policy import ensure_available


async def switch_version(
    session, *, conversation_id, user_id, target_snapshot_id, automatic=False
) -> VersionSwitched:
    async with session.begin():
        conversation = await owned_conversation(
            session, conversation_id, user_id, lock=True
        )
        if not conversation.product_snapshot_id:
            raise ValueError("Legacy version is not verified.")
        if conversation.product_snapshot_id == target_snapshot_id:
            return VersionSwitched(snapshot_id=target_snapshot_id, changed=False)
        current = await session.get(ProductSnapshot, conversation.product_snapshot_id)
        target = await session.scalar(
            select(ProductSnapshot).where(
                ProductSnapshot.id == target_snapshot_id,
                ProductSnapshot.product_id == conversation.product_id,
            )
        )
        if target is None:
            raise LookupError("Version not found.")
        await ensure_available(session, target.id)
        if target.version <= current.version:
            raise ValueError("Only forward version transitions are supported.")
        # Every intermediate release must permit automatic application.
        notes = list(
            await session.execute(
                select(ProductSnapshot, ProductReleaseNote)
                .outerjoin(
                    ProductReleaseNote,
                    ProductReleaseNote.product_snapshot_id == ProductSnapshot.id,
                )
                .where(
                    ProductSnapshot.product_id == conversation.product_id,
                    ProductSnapshot.version > current.version,
                    ProductSnapshot.version <= target.version,
                )
            )
        )
        if not notes or any(n is None for _, n in notes):
            raise ValueError("Release notes missing; transition unavailable.")
        if automatic and any(n.update_policy != "automatic" for _, n in notes):
            raise ValueError("Customer consent required for this transition.")
        characters = list(
            await session.scalars(
                select(ProductSnapshotCharacter).where(
                    ProductSnapshotCharacter.product_snapshot_id == target.id
                )
            )
        )
        if not characters or sum(c.is_primary for c in characters) != 1:
            raise ValueError("Invalid target composition.")
        await session.execute(
            delete(ConversationCharacter).where(
                ConversationCharacter.conversation_id == conversation.id
            )
        )
        for c in characters:
            source = await session.get(CharacterSnapshot, c.character_snapshot_id)
            session.add(
                ConversationCharacter(
                    conversation_id=conversation.id,
                    character_id=source.character_id,
                    product_character_id=c.id,
                    role_order=c.role_order,
                )
            )
        changed_at = datetime.now(UTC)
        session.add(
            ConversationVersionChange(
                created_at=changed_at,
                conversation_id=conversation.id,
                from_snapshot_id=current.id,
                to_snapshot_id=target.id,
                mode="automatic" if automatic else "choice",
            )
        )
        conversation.product_snapshot_id = target.id
        conversation.is_group = len(characters) > 1
        conversation.active_model_id = None
        # Initial context, messages and memory remain untouched, including removed characters.
        await session.flush()
        await mark_dirty(session, conversation.product_id, changed_at)
        return VersionSwitched(snapshot_id=target.id, changed=True)
