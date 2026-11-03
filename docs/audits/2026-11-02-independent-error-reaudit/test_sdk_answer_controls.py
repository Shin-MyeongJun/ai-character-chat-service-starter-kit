"""Full answer settlement in PG with installed OpenAI SDK; no provider network."""
import asyncio

import httpx
import openai
import pytest

from app.modules.chatting.chat import types as ChatTypes
from app.modules.llm.adapters.openai import OpenAIAdapter
from app.modules.llm.service.text_generation import TextGenerationService
from test_answer_billing_integration import check_state
from test_nonstream_answers import setup_answer


@pytest.mark.asyncio
@pytest.mark.parametrize('cause', ['deadline', 'caller_cancel'])
async def test_installed_sdk_answer_is_not_charged_after_cancel(db, cause):
    orchestrator, command, _ = await setup_answer(db, config=ChatTypes.AnswerConfig(timeout_seconds=3))
    entered = asyncio.Event()
    never = asyncio.Event()
    cancelled = []

    async def transport(_request):
        entered.set()
        try:
            await never.wait()
        except asyncio.CancelledError:
            cancelled.append(True)
            raise
        raise AssertionError('Unreachable')

    client = openai.AsyncOpenAI(
        api_key='audit-placeholder', max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(transport), trust_env=False),
    )
    orchestrator.text = TextGenerationService([OpenAIAdapter(client=client)])
    task = asyncio.create_task(orchestrator.generate_answer(command))
    try:
        await asyncio.wait_for(entered.wait(), 5)
        if cause == 'caller_cancel':
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            status = 'cancelled'
        else:
            answer = await asyncio.wait_for(task, 10)
            assert answer.status == 'failed' and answer.error_code == 'timeout'
            status = 'failed'
        assert cancelled == [True]
        await check_state(orchestrator, command, status=status, balance=20, reserved=0, charge=0)
        print(f'CONTROL installed_openai_sdk_pg cause={cause} status={status} debit=0 balance=20 reserved=0')
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await orchestrator.text.aclose()
