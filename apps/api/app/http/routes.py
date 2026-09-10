from fastapi import APIRouter

from app.modules.chatting.chat.router import router as MessagesRouter
from app.modules.chatting.conversation.router import router as Router1
from app.modules.content.character.router import router as Router3
from app.modules.content.lorebook.router import router as Router4
from app.modules.content.product.router import router as Router5
from app.modules.governance.admin.character_router import router as Router6
from app.modules.governance.admin.lorebook_router import router as Router7
from app.modules.governance.admin.model_router import router as Router8
from app.modules.governance.admin.product_router import router as Router9
from app.modules.governance.moderation.character_router import router as Router11
from app.modules.governance.moderation.lorebook_router import router as Router12

"""Application router assembly: owner routes precede administrative UUID routes."""

router = APIRouter()

router.include_router(Router1)

router.include_router(Router3)

router.include_router(Router4)

router.include_router(Router5)

router.include_router(Router6)

router.include_router(Router7)

router.include_router(Router8)

router.include_router(Router9)

router.include_router(Router11)

router.include_router(Router12)
router.include_router(MessagesRouter)
