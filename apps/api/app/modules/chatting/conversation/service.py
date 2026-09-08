"""Conversation commands own transactions. Runtime context is internal, not an HTTP DTO."""
from uuid import uuid4
from sqlalchemy import select
from app.db.models.chat import Conversation, ConversationCharacter, Message
from app.db.models.product import Product
from app.db.models.snapshot.product import ProductSnapshot, ProductSnapshotCharacter, ProductSnapshotLorebook, ProductSnapshotStartSet, ProductSnapshotLorebookCharacter
from app.db.models.snapshot.character import CharacterSnapshot
from app.db.models.snapshot.lorebook import LorebookSnapshot


async def owned_conversation(session, conversation_id, user_id, *, lock=False):
    stmt=select(Conversation).where(Conversation.id==conversation_id,Conversation.user_id==user_id)
    if lock:
        stmt=stmt.with_for_update().execution_options(populate_existing=True)
    conversation=await session.scalar(stmt)
    if conversation is None:
        raise LookupError('Conversation not found.')
    return conversation


async def start_conversation(session, *, product_id, user_id, start_set_id=None):
    async with session.begin():
        product=await session.scalar(select(Product).where(Product.id==product_id).with_for_update(read=True))
        if product is None or (product.owner_id != user_id and (product.status != 'approved' or product.visibility == 'private')):
            raise LookupError('Product not found.')
        if not product.latest_snapshot_id:
            raise ValueError('Product has no published version.')
        snapshot=await session.get(ProductSnapshot,product.latest_snapshot_id)
        starts=list(await session.scalars(select(ProductSnapshotStartSet).where(ProductSnapshotStartSet.product_snapshot_id==snapshot.id).order_by(ProductSnapshotStartSet.sort_order)))
        if start_set_id is None and len(starts)==1:
            start_set_id=starts[0].id
        if start_set_id not in {s.id for s in starts}:
            raise ValueError('Choose exactly one start option from this version.')
        characters=list(await session.scalars(select(ProductSnapshotCharacter).where(ProductSnapshotCharacter.product_snapshot_id==snapshot.id)))
        primary=next((c for c in characters if c.is_primary),None)
        if primary is None:
            raise ValueError('Version has no primary character.')
        conversation=Conversation(id=uuid4(),user_id=user_id,product_id=product_id,product_snapshot_id=snapshot.id,start_set_id=start_set_id,is_group=len(characters)>1,title=snapshot.snapshot_data['title'])
        session.add(conversation)
        await session.flush()
        for c in characters:
            source=await session.get(CharacterSnapshot,c.character_snapshot_id)
            session.add(ConversationCharacter(conversation_id=conversation.id,character_id=source.character_id,product_character_id=c.id,role_order=c.role_order))
        source=await session.get(CharacterSnapshot,primary.character_snapshot_id)
        session.add(Message(conversation_id=conversation.id,sender_type='character',character_id=source.character_id,product_character_id=primary.id,product_snapshot_id=snapshot.id,content=snapshot.snapshot_data['opening_message'],generated_by_ai=False))
        await session.flush()
        return {'id':conversation.id,'product_snapshot_id':snapshot.id,'start_set_id':start_set_id}


async def runtime_context(session, *, conversation_id, user_id):
    conversation=await owned_conversation(session,conversation_id,user_id)
    if conversation.product_snapshot_id is None:
        raise ValueError('Legacy conversation requires verified version mapping.')
    snapshot=await session.get(ProductSnapshot,conversation.product_snapshot_id)
    start=await session.get(ProductSnapshotStartSet,conversation.start_set_id)
    chars=list(await session.scalars(select(ProductSnapshotCharacter).where(ProductSnapshotCharacter.product_snapshot_id==snapshot.id).order_by(ProductSnapshotCharacter.role_order)))
    books=list(await session.scalars(select(ProductSnapshotLorebook).where(ProductSnapshotLorebook.product_snapshot_id==snapshot.id).order_by(ProductSnapshotLorebook.priority.desc())))
    targets=list(await session.scalars(select(ProductSnapshotLorebookCharacter).where(ProductSnapshotLorebookCharacter.product_snapshot_id==snapshot.id)))
    character_data=[]
    for c in chars:
        character_data.append({'id':str(c.id),'snapshot_id':str(c.character_snapshot_id),'primary':c.is_primary,'data':(await session.get(CharacterSnapshot,c.character_snapshot_id)).snapshot_data})
    book_data=[]
    for b in books:
        data=(await session.get(LorebookSnapshot,b.lorebook_snapshot_id)).snapshot_data
        book_data.append({'id':str(b.id),'scope':b.scope,'targets':[str(t.product_character_id) for t in targets if t.product_lorebook_id==b.id], 'entries':[e for e in data['entries'] if e['entry_type']!='start_set' and e['is_enabled']]})
    return {'product_snapshot_id':str(snapshot.id),'settings':snapshot.snapshot_data,'start':{'title':start.title,'content':start.content},'characters':character_data,'lorebooks':book_data}
