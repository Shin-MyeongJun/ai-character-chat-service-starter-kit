"""Check the named local test account, saved runs, and replay without new generation."""
import asyncio
import json
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

async def main():
    load_dotenv('.env.local', override=True)
    work = json.loads(Path('tmp/local-runtime/test-work.json').read_text())
    engine = create_async_engine(os.environ['DATABASE_URL'])
    async with engine.connect() as db:
        rows = (await db.execute(text('SELECT id, conversation_id, model_name, status, request_key, answer_metadata FROM product_generations WHERE user_id=:u ORDER BY created_at'), {'u': work['user_id']})).mappings().all()
        runs = [dict(r) for r in rows]
        print('runs', json.dumps([{'id':str(r['id']), 'model':r['model_name'], 'status':r['status'], 'estimate':(r['answer_metadata'] or {}).get('estimated_prompt_tokens')} for r in runs]))
        usage = (await db.execute(text('SELECT model_id,input_tokens,output_tokens,cost_credit FROM usage_logs WHERE user_id=:u ORDER BY created_at'), {'u':work['user_id']})).mappings().all()
        print('usage', json.dumps([dict(r) for r in usage],default=str))
        tokens = (await db.execute(text('SELECT purpose,consumed_at IS NOT NULL AS consumed FROM auth_action_tokens WHERE user_id=:u'), {'u':work['user_id']})).mappings().all()
        print('auth_tokens',json.dumps([dict(r) for r in tokens]))
        snapshots = (await db.execute(text('SELECT id,product_snapshot_id,initial_snapshot_id FROM conversations WHERE user_id=:u AND product_id=:p ORDER BY created_at'),{'u':work['user_id'],'p':work['product_id']})).mappings().all()
        print('conversation_snapshots',json.dumps([dict(r) for r in snapshots],default=str))
        character_count = await db.scalar(text('SELECT count(*) FROM product_snapshot_characters WHERE product_snapshot_id=:s'), {'s':work['real_release']['snapshot_id']})
        start_count = await db.scalar(text('SELECT count(*) FROM product_snapshot_start_sets WHERE product_snapshot_id=:s'), {'s':work['real_release']['snapshot_id']})
        print('published_counts', json.dumps({'characters':character_count,'starts':start_count}))
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8000',headers={'Origin':'http://localhost:3000'},timeout=30) as client:
        print('anonymous_private_catalog', (await client.get('/products/catalog/'+work['product_id'])).status_code)
        print('anonymous_messages', (await client.get('/conversations/6ccdbd95-c6b0-4b52-ad92-43e31190407e/messages')).status_code)
        csrf = (await client.get('/auth/csrf')).json()['csrf_token']
        client.headers['X-CSRF-Token']=csrf
        print('old_password', (await client.post('/auth/login',json={'email':'hogwarts-test-20261008@example.com','password':'ChatkitTest2026!'})).status_code)
        login=await client.post('/auth/login',json={'email':'hogwarts-test-20261008@example.com','password':os.environ['LOCAL_TEST_PASSWORD']})
        assert login.status_code==200
        print('new_password',login.status_code)
        print('owner_detail',(await client.get('/products/'+work['product_id'])).status_code)
        draft=(await client.get('/products/'+work['product_id']+'/studio-draft')).json()['document']
        source=json.loads(Path('tmp/local-runtime/hogwarts-studio.json').read_text(encoding='utf-8'))
        print('draft_content_preserved', all(draft[k]==source[k] for k in ('characters','lorebooks','scenes')))
        print('draft_counts',json.dumps({k:len(draft[k]) for k in ('characters','lorebooks','scenes')}))
        before=(await client.get('/account/credits')).json()
        run=next(r for r in runs if r['model_name']=='mock-hogwarts' and r['status']=='succeeded')
        payload={'request_key':run['request_key'],**run['answer_metadata']['identity']}
        payload.pop('conversation_id',None)
        url=f"/conversations/{run['conversation_id']}/answers"
        client.headers.pop('X-CSRF-Token')
        print('missing_csrf',(await client.post(url,json=payload)).status_code)
        client.headers['X-CSRF-Token']=csrf
        replay=await client.post(url,json=payload)
        after=(await client.get('/account/credits')).json()
        print('duplicate_replay',replay.status_code,replay.json().get('status'),'credit_unchanged',before==after)
        print('credits',json.dumps(after))
    await engine.dispose()

asyncio.run(main())
