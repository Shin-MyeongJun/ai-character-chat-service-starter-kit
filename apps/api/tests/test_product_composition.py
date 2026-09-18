# 상품 초안 구성의 중복·대표 캐릭터·로어 적용 범위 검증을 확인한다.
from uuid import uuid4

import pytest
from app.modules.content.product.service.command.composition import (
    _validate_composition as validate,
)
from app.modules.content.product.types import (
    CharacterSelection,
    LorebookSelection,
    ProductCompositionInfo,
)


def test_invalid_targets_and_duplicate_primary():
    a, b = uuid4(), uuid4()
    invalid = [
        ProductCompositionInfo(
            (CharacterSelection(a, True), CharacterSelection(b, True))
        ),
        ProductCompositionInfo(
            (CharacterSelection(a),), (LorebookSelection(uuid4(), "selected", (b,)),)
        ),
        ProductCompositionInfo((), (LorebookSelection(uuid4(), "selected"),)),
        ProductCompositionInfo(
            (CharacterSelection(a),), (LorebookSelection(uuid4(), "all", (a,)),)
        ),
    ]
    for value in invalid:
        with pytest.raises(ValueError):
            validate(value)
