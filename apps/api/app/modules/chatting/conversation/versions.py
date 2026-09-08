from sqlalchemy import delete, select
from app.db.models.chat import ConversationCharacter, ConversationVersionChange, Message
from app.db.models.product_release import ProductReleaseNote
from app.db.models.snapshot.product import ProductSnapshot, ProductSnapshotCharacter
from app.db.models.snapshot.character import CharacterSnapshot
from app.modules.chatting.conversation.service import owned_conversation


async def switch_version(session, *, conversation_id, user_id, target_snapshot_id, automatic=False):
    async with session.begin():
        conversation=await owned_conversation(session,conversation_id,user_id,lock=True)
        if not conversation.product_snapshot_id:
            raise ValueError('Legacy version is not verified.')
        if conversation.product_snapshot_id==target_snapshot_id:
            return {'snapshot_id':target_snapshot_id,'changed':False}
        current=await session.get(ProductSnapshot,conversation.product_snapshot_id)
        target=await session.scalar(select(ProductSnapshot).where(ProductSnapshot.id==target_snapshot_id,ProductSnapshot.product_id==conversation.product_id))
        if target is None:
            raise LookupError('Version not found.')
        if target.version<=current.version:
            raise ValueError('Only forward version transitions are supported.')
        # Every intermediate release must permit automatic application.
        notes=list(await session.execute(select(ProductSnapshot,ProductReleaseNote).outerjoin(ProductReleaseNote,ProductReleaseNote.product_snapshot_id==ProductSnapshot.id).where(ProductSnapshot.product_id==conversation.product_id,ProductSnapshot.version>current.version,ProductSnapshot.version<=target.version)))
        if not notes or any(n is None for _,n in notes):
            raise ValueError('Release notes missing; transition unavailable.')
        if automatic and any(n.update_policy!='automatic' for _,n in notes):
            raise ValueError('Customer consent required for this transition.')
        characters=list(await session.scalars(select(ProductSnapshotCharacter).where(ProductSnapshotCharacter.product_snapshot_id==target.id)))
        if not characters or sum(c.is_primary for c in characters)!=1:
            raise ValueError('Invalid target composition.')
        await session.execute(delete(ConversationCharacter).where(ConversationCharacter.conversation_id==conversation.id))
        for c in characters:
            source=await session.get(CharacterSnapshot,c.character_snapshot_id)
            session.add(ConversationCharacter(conversation_id=conversation.id,character_id=source.character_id,product_character_id=c.id,role_order=c.role_order))
        session.add(ConversationVersionChange(conversation_id=conversation.id,from_snapshot_id=current.id,to_snapshot_id=target.id,mode='automatic' if automatic else 'choice'))
        conversation.product_snapshot_id=target.id
        conversation.is_group=len(characters)>1
        conversation.active_model_id=None
        # Initial context, messages and memory remain untouched, including removed characters.
        await session.flush()
        return {'snapshot_id':target.id,'changed':True}


async def append_generated_message(session, *, conversation_id, user_id, expected_snapshot_id, product_character_id, content, model_id):
    """Chat orchestration supplies the version captured before calling the LLM."""
    if not content.strip() or len(content)>200000:
        raise ValueError('Invalid generated content.')
    async with session.begin():
        conversation=await owned_conversation(session,conversation_id,user_id,lock=True)
        if conversation.product_snapshot_id!=expected_snapshot_id:
            raise ValueError('Version changed during generation; discard stale completion.')
        character=await session.scalar(select(ProductSnapshotCharacter).where(ProductSnapshotCharacter.id==product_character_id,ProductSnapshotCharacter.product_snapshot_id==expected_snapshot_id))
        if character is None:
            raise ValueError('Character is not part of the execution version.')
        source=await session.get(CharacterSnapshot,character.character_snapshot_id)
        message=Message(conversation_id=conversation.id,product_snapshot_id=expected_snapshot_id,product_character_id=character.id,character_id=source.character_id,sender_type='character',content=content,model_id=model_id,generated_by_ai=True)
        session.add(message)
        await session.flush()
        return message.id
