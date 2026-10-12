from types import SimpleNamespace
from uuid import uuid4

from app.modules.chatting.chat.mapper.schema.answers import answer_info_to_response
from app.modules.chatting.chat.service.workflow.answers import _answer_info


def test_answer_response_exposes_reserved_price_when_quote_exists():
    run = SimpleNamespace(
        id=uuid4(), status="succeeded", model_name="test-model",
        answer_metadata={"content": "Hello", "billing": {"reserved_credit": 42}},
    )
    response = answer_info_to_response(_answer_info(run))
    assert response.price_credit == 42
    assert response.content == "Hello"


def test_legacy_answer_response_has_no_invented_price():
    run = SimpleNamespace(id=uuid4(), status="succeeded", model_name="test-model", answer_metadata={"content": "Hello"})
    assert answer_info_to_response(_answer_info(run)).price_credit is None
