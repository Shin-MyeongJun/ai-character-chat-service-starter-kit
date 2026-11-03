"""Actual studio HTTP router/DTO, PG services; only identity is preauthenticated."""
import asyncio
from copy import deepcopy
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import event, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.snapshot.product import ProductSnapshot
from app.http import dependencies, studio_publication
from app.modules.content.tag import types as TagTypes
from app.modules.content.tag.service import command as TagCommand
from test_product_integration import ready_product
from test_studio_publication import document


def http_app(db, owner):
    app = FastAPI()
    app.include_router(studio_publication.router)

    async def session():
        async with AsyncSession(db.bind, expire_on_commit=False) as value:
            yield value

    app.dependency_overrides[dependencies.get_product_session] = session
    app.dependency_overrides[dependencies.get_current_owner_id] = lambda: owner
    return app


async def save(client, product, revision, value):
    response = await client.put(f'/products/{product}/studio-draft', json={
        'expected_revision': revision, 'document': value,
    })
    assert response.status_code == 200, 'Draft save failed'
    return response.json()['revision']


def request(revision, model):
    return {'expected_revision': revision, 'model_id': str(model), 'reasoning_effort': 'low',
            'summary': 'Audit', 'body': 'Synthetic audit release'}


@pytest.mark.asyncio
async def test_http_noop_publication_replay_after_new_save(db):
    owner, _, _, _, model, _ = await ready_product(db)
    app = http_app(db, owner.id)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://audit.invalid') as client:
        product = uuid4()
        value = document()
        edited = deepcopy(value)
        edited['work']['title'] = 'Synthetic edit'
        revision = await save(client, product, None, value)
        url = f'/products/{product}/studio-publication'
        first = await client.post(url, json=request(revision, model.id))
        assert first.status_code == 200
        revision = await save(client, product, revision, edited)
        revision = await save(client, product, revision, value)
        accepted_request = request(revision, model.id)
        accepted = await client.post(url, json=accepted_request)
        assert accepted.status_code == 200 and accepted.json() == first.json()
        # Same-revision replay currently succeeds: the failure needs a subsequent save.
        immediate = await client.post(url, json=accepted_request)
        assert immediate.status_code == 200 and immediate.json() == first.json()
        await save(client, product, revision, edited)
        replay = await client.post(url, json=accepted_request)
        original_replay = await client.post(url, json=request(1, model.id))
        assert original_replay.status_code == 200 and original_replay.json() == first.json()
        print(f'HTTP noop accepted={accepted.status_code} immediate={immediate.status_code} later_replay={replay.status_code} original_receipt_replay={original_replay.status_code}')
        assert replay.status_code == 200, 'Previously accepted no-op request now returns HTTP 409'


@pytest.mark.asyncio
@pytest.mark.parametrize('preexisting', [False, True])
async def test_http_two_publications_cross_component_tags(db, monkeypatch, preexisting):
    owner, _, _, _, model, _ = await ready_product(db)
    names = ('reaudit-alpha', 'reaudit-beta')
    if preexisting:
        await TagCommand.resolve_tags(db, TagTypes.ResolveTagsCommand(names))
    app = http_app(db, owner.id)
    barrier = asyncio.Barrier(2)
    original = TagCommand.resolve_tags
    pids = set()
    sqlstates = []

    async def gated(session, command):
        result = await original(session, command)
        if not session.info.get('reaudit_gated'):
            session.info['reaudit_gated'] = True
            await session.execute(text("SET LOCAL statement_timeout = '8s'"))
            pids.add(await session.scalar(text('SELECT pg_backend_pid()')))
            await asyncio.wait_for(barrier.wait(), 5)
        return result

    def on_error(context):
        state = getattr(context.original_exception, 'sqlstate', None)
        if state:
            sqlstates.append(state)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url='http://audit.invalid') as client:
        products = [uuid4(), uuid4()]
        revisions = []
        for product, (first, second) in zip(products, [names, names[::-1]], strict=True):
            value = document()
            value['characters'][0]['tags'] = [first]
            value['lorebooks'][0]['tags'] = [second]
            revisions.append(await save(client, product, None, value))
        monkeypatch.setattr(TagCommand, 'resolve_tags', gated)
        event.listen(db.bind.sync_engine, 'handle_error', on_error)
        try:
            responses = await asyncio.wait_for(asyncio.gather(*(
                client.post(f'/products/{p}/studio-publication', json=request(r, model.id))
                for p, r in zip(products, revisions, strict=True)
            )), 15)
        finally:
            event.remove(db.bind.sync_engine, 'handle_error', on_error)
            monkeypatch.setattr(TagCommand, 'resolve_tags', original)
        assert len(pids) == 2
        statuses = sorted(r.status_code for r in responses)
        async with db.begin():
            before_retry = await db.scalar(select(func.count()).select_from(ProductSnapshot))
        # Both the rolled-back request and successful receipt can be retried safely.
        retries = [await client.post(f'/products/{p}/studio-publication', json=request(r, model.id))
                   for p, r in zip(products, revisions, strict=True)]
        assert [r.status_code for r in retries] == [200, 200]
        async with db.begin():
            after_retry = await db.scalar(select(func.count()).select_from(ProductSnapshot))
        assert after_retry == 2
        print(f'HTTP tags preexisting={preexisting} separate_connections={len(pids)} statuses={statuses} sqlstates={sqlstates} snapshots_before_retry={before_retry} snapshots_after_retry={after_retry} retries=[200,200]')
        assert statuses == [200, 200], 'Valid concurrent studio publications produce HTTP 500'
