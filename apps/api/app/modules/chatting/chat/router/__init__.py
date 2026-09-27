"""HTTP entry points owned by chat."""

from fastapi import APIRouter

from app.modules.chatting.chat.router.answers import router as AnswersRouter
from app.modules.chatting.chat.router.messages import router as MessagesRouter

router = APIRouter()
router.include_router(MessagesRouter)
router.include_router(AnswersRouter)
