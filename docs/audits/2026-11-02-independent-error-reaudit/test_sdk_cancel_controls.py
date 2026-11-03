"""Installed SDK + production adapter, fake HTTP transport only; no sockets."""
import asyncio

import anthropic
import httpx
import openai
import pytest

from app.modules.llm.adapters.anthropic import AnthropicAdapter
from app.modules.llm.adapters.openai import OpenAIAdapter
from app.modules.llm.service.text_generation import TextGenerationService
from app.modules.llm.types import GenerateTextCommand


@pytest.mark.asyncio
@pytest.mark.parametrize('provider', ['openai', 'anthropic'])
@pytest.mark.parametrize('cause', ['deadline', 'caller_cancel'])
async def test_installed_sdk_propagates_cancellation(provider, cause):
    entered = asyncio.Event()
    never = asyncio.Event()
    seen = []
    deadline = None

    async def transport(_request):
        if cause == 'deadline':
            deadline.reschedule(asyncio.get_running_loop().time() + 0.25)
        entered.set()
        try:
            await never.wait()
        except asyncio.CancelledError:
            seen.append('cancelled')
            raise
        raise AssertionError('Unreachable')

    http = httpx.AsyncClient(transport=httpx.MockTransport(transport), trust_env=False)
    if provider == 'openai':
        client = openai.AsyncOpenAI(api_key='audit-placeholder', http_client=http, max_retries=0)
        adapter, model = OpenAIAdapter(client=client), 'gpt-test'
    else:
        client = anthropic.AsyncAnthropic(api_key='audit-placeholder', http_client=http, max_retries=0)
        adapter, model = AnthropicAdapter(client=client), 'claude-test'
    service = TextGenerationService([adapter])

    async def run():
        nonlocal deadline
        # Arm at transport entry, excluding one-time SDK lazy import overhead.
        async with asyncio.timeout(10) as deadline:
            return await service.generate_text(GenerateTextCommand('synthetic', model=model, provider=provider))

    task = asyncio.create_task(run())
    try:
        await asyncio.wait_for(entered.wait(), 5)
        if cause == 'caller_cancel':
            task.cancel()
        expected = TimeoutError if cause == 'deadline' else asyncio.CancelledError
        with pytest.raises(expected):
            await task
        assert seen == ['cancelled']
        print(f'CONTROL installed_sdk={provider} cause={cause} transport_cancelled=True result_returned=False')
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await service.aclose()
