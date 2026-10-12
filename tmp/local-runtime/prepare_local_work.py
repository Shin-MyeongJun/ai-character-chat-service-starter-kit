"""Seed mock prerequisites and upload the converted studio document via HTTP."""
import asyncio
import json
import os
from pathlib import Path
from uuid import UUID, uuid4, uuid5, NAMESPACE_URL

import httpx
from dotenv import load_dotenv, set_key
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.db.models.model_routing import Model, Provider
from app.modules.commerce.credit import types as CreditTypes
from app.modules.commerce.credit.service import command as CreditCommand

root = Path(__file__).parent.resolve()
load_dotenv('.env.local', override=True)
email = 'hogwarts-test-20261008@example.com'

def checked(response):
    if response.status_code >= 400:
        raise RuntimeError(f'{response.request.method} {response.request.url.path}: {response.status_code} {response.text[:500]}')
    return response.json() if response.content else None

async def main():
    project = json.loads((root / 'hogwarts-studio.json').read_text(encoding='utf-8'))
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8000', headers={'Origin': 'http://localhost:3000'}, timeout=60) as client:
        csrf = checked(await client.get('/auth/csrf'))['csrf_token']
        client.headers['X-CSRF-Token'] = csrf
        user = checked(await client.post('/auth/login', json={'email': email, 'password': os.environ['LOCAL_TEST_PASSWORD']}))
        products = checked(await client.get('/products/mine'))
        product = next(row for row in products if row['title'] == project['work']['title'])
        prior = checked(await client.get(f"/products/{product['id']}/studio-draft"))
        project['clientWorkId'] = prior['document'].get('clientWorkId', product['id'])
        draft = checked(await client.put(f"/products/{product['id']}/studio-draft", json={'expected_revision': prior['revision'], 'document': project}))
        model_id = uuid5(NAMESPACE_URL, 'chatkit-local:mock-hogwarts-model')
        engine = create_async_engine(os.environ['DATABASE_URL'])
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            async with session.begin():
                provider = await session.scalar(select(Provider).where(Provider.name == 'mock'))
                if not provider:
                    provider = Provider(id=uuid4(), name='mock')
                    session.add(provider)
                    await session.flush()
                model = await session.get(Model, model_id)
                if not model:
                    session.add(Model(id=model_id, provider_id=provider.id, model_name='mock-hogwarts',
                        display_name='로컬 Mock · 호그와트 검증', context_window=131072,
                        input_price=0, output_price=0,
                        capabilities={'reasoning_efforts':['none'],'model_family':'local-test'}))
            async with session.begin():
                await CreditCommand.grant_credit(session, CreditTypes.GrantCreditCommand(
                    user_id=UUID(user['id']), currency_code='CREDIT', bucket=CreditTypes.CreditBucket.FREE,
                    amount=1000, reason='local_test', reference_id=UUID(product['id']),
                    namespace='local-ui-test', request_key=uuid5(NAMESPACE_URL,'chatkit-local:hogwarts-ui-test-grant')))
        await engine.dispose()
        prices = {'price_book': {'version':'local-mock-v1','currency':'TEST',
            'credits_per_currency_unit':'1','safety_factor':'1', 'models':[{
                'execution': {'model_id':str(model_id),'provider':'mock','model':'mock-hogwarts','reasoning_effort':'none'},
                'input_cost_per_token':'0','output_cost_per_token':'0',
                'tiers':[{'tier_id':'local-test','min_context_tokens':0,'max_context_tokens_exclusive':131072,'normal_price_credit':'10'}]}]},
            'quote_ttl_seconds':60}
        price_path = root / 'mock-prices.json'
        price_path.write_text(json.dumps(prices,ensure_ascii=False,indent=2),encoding='utf-8')
        for key,value in {'BILLING_PRICING_CONFIG_PATH':str(price_path),'MAX_PROMPT_TOKENS':'48000',
            'MEMORY_SUMMARY_THRESHOLD_TOKENS':'60000'}.items(): set_key('.env.local',key,value)
        result = {'user_id':user['id'],'product_id':product['id'],'model_id':str(model_id),
            'revision':draft['revision'],'characters':len(project['characters']),
            'lore_entries':len(project['lorebooks']),'scenes':len(project['scenes'])}
        (root/'test-work.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result))

asyncio.run(main())
