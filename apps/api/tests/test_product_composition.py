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
