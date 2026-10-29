from typing import cast

from fastapi import HTTPException, Request

from app.modules.chatting.chat.service.workflow.answers import AnswerOrchestrator


def get_answer_orchestrator(request: Request) -> AnswerOrchestrator:
    value = getattr(request.app.state, "answer_orchestrator", None)
    if value is None:
        raise HTTPException(503, "Answer runtime is not configured.")
    # main installs AnswerOrchestrator here; retain injected test/runtime doubles.
    return cast(AnswerOrchestrator, value)
