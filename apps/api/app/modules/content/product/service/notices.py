from sqlalchemy import select
from app.db.models.product import Product
from app.db.models.product_release import ProductReleaseNote
from app.db.models.snapshot.product import ProductSnapshot, ProductSnapshotStartSet
from app.modules.chatting.conversation.service import owned_conversation


async def published_product(session, *, product_id, user_id):
    product=await session.get(Product,product_id)
    if product is None or (product.owner_id != user_id and (product.status!='approved' or product.visibility=='private')):
        raise LookupError('Product not found.')
    if product.latest_snapshot_id is None:
        raise LookupError('Published product not found.')
    snapshot=await session.get(ProductSnapshot,product.latest_snapshot_id)
    starts=list(await session.scalars(select(ProductSnapshotStartSet).where(ProductSnapshotStartSet.product_snapshot_id==snapshot.id).order_by(ProductSnapshotStartSet.sort_order)))
    return {'product_id':product.id,'snapshot_id':snapshot.id,'version':snapshot.version,'title':snapshot.snapshot_data['title'],'description':snapshot.snapshot_data['description'], 'start_options':[{'id':s.id,'title':s.title} for s in starts]}


async def pending_updates(session, *, conversation_id, user_id):
    conversation=await owned_conversation(session,conversation_id,user_id)
    if not conversation.product_snapshot_id:
        raise ValueError('Legacy conversation requires verified version mapping.')
    current=await session.get(ProductSnapshot,conversation.product_snapshot_id)
    product=await session.get(Product,conversation.product_id)
    rows=await session.execute(select(ProductSnapshot,ProductReleaseNote).join(ProductReleaseNote,ProductReleaseNote.product_snapshot_id==ProductSnapshot.id).where(ProductSnapshot.product_id==conversation.product_id,ProductSnapshot.version>current.version).order_by(ProductSnapshot.version))
    updates=[{'snapshot_id':s.id,'version':s.version,'summary':n.summary,'body':n.body,'change_kind':n.change_kind,'update_policy':n.update_policy,'expires_at':s.expires_at} for s,n in rows]
    return {'current_snapshot_id':current.id,'current_expires_at':current.expires_at,'expiry_reason':current.expiry_reason,'latest_snapshot_id':product.latest_snapshot_id,'updates':updates}
