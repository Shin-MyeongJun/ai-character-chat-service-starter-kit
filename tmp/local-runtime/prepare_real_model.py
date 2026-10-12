"""Keep v1 intact; publish the same nonsexual content as v2 with the configured LLM."""
import asyncio
import json
import os
from pathlib import Path
from uuid import uuid4, uuid5, NAMESPACE_URL
import httpx
from dotenv import dotenv_values, load_dotenv, set_key
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.db.models.model_routing import Model, Provider

root = Path(__file__).parent.resolve()
load_dotenv('.env.local', override=True)
original = dotenv_values('.env')
model_name = original['LOCAL_TEST_MODEL']
assert model_name == 'gpt-4o-mini', 'Verify the configured model before changing its limits.'
assert original.get('OPENAI_API_KEY'), 'OpenAI key is missing.'
work = json.loads((root/'test-work.json').read_text())

def checked(response):
    if response.status_code >= 400:
        raise RuntimeError(f'{response.request.url.path}: {response.status_code} {response.text[:300]}')
    return response.json()

async def main():
    model_id = uuid5(NAMESPACE_URL, f'chatkit-local:{model_name}')
    engine = create_async_engine(os.environ['DATABASE_URL'])
    sessions = async_sessionmaker(engine,expire_on_commit=False)
    async with sessions() as session, session.begin():
        provider = await session.scalar(select(Provider).where(Provider.name=='openai'))
        if not provider:
            provider=Provider(id=uuid4(),name='openai');session.add(provider);await session.flush()
        if not await session.get(Model, model_id):
            session.add(Model(id=model_id,provider_id=provider.id,model_name=model_name,
                display_name='실제 OpenAI · gpt-4o-mini', context_window=128000,
                input_price='0.15',output_price='0.60',capabilities={'reasoning_efforts':['none'],'model_family':'gpt-4o'}))
        starts=[str(value) for value in (await session.execute(text('SELECT entry_id FROM product_start_sets WHERE product_id=:id ORDER BY sort_order'),{'id':work['product_id']})).scalars()]
    await engine.dispose()
    price_path=root/'mock-prices.json'
    prices=json.loads(price_path.read_text())
    if not any(m['execution']['model_id']==str(model_id) for m in prices['price_book']['models']):
        prices['price_book']['models'].append({'execution':{'model_id':str(model_id),'provider':'openai','model':model_name,'reasoning_effort':'none'},
            'input_cost_per_token':'0.00000015','output_cost_per_token':'0.00000060',
            'tiers':[{'tier_id':'local-real-test','min_context_tokens':0,'max_context_tokens_exclusive':128000,'normal_price_credit':'10'}]})
    price_path.write_text(json.dumps(prices,indent=2),encoding='utf-8')
    set_key('.env.local','OPENAI_API_KEY',original['OPENAI_API_KEY'])
    set_key('.env.local','MAX_PROMPT_TOKENS','122000')
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8000',headers={'Origin':'http://localhost:3000'},timeout=60) as client:
        client.headers['X-CSRF-Token']=checked(await client.get('/auth/csrf'))['csrf_token']
        checked(await client.post('/auth/login',json={'email':'hogwarts-test-20261008@example.com','password':os.environ['LOCAL_TEST_PASSWORD']}))
        checked(await client.put(f"/products/{work['product_id']}/settings",json={'model_id':str(model_id),'reasoning_effort':'none','start_entry_ids':starts}))
        release=checked(await client.post(f"/products/{work['product_id']}/releases",json={'summary':'실제 gpt-4o-mini 채팅 검증','body':'비성적 CHARX 변환 설정을 그대로 보존하고 실행 모델을 OpenAI gpt-4o-mini로 변경한 로컬 테스트 버전.'}))
    work['real_model_id']=str(model_id);work['real_release']=release
    (root/'test-work.json').write_text(json.dumps(work,indent=2),encoding='utf-8')
    print(json.dumps({'model':model_name,'version':release['version'],'snapshot_id':release['snapshot_id']}))

asyncio.run(main())
