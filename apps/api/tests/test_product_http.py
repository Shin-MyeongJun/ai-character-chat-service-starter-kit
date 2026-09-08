from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.modules.content.product.router import router
from app.modules.chatting.conversation.router import router as conversations


def test_product_and_conversation_contracts_are_registered():
    app=FastAPI()
    app.include_router(router)
    app.include_router(conversations)
    schema=app.openapi()
    assert '/products/{product_id}/releases' in schema['paths']
    assert '/conversations/{conversation_id}/updates' in schema['paths']
    with TestClient(app) as client:
        assert client.post('/products',json={'title':'P','owner_id':'forged'}).status_code != 201
