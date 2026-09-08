from uuid import uuid4

import pytest
from app.modules.content.product.service.composition import validate
from app.modules.content.product.types import (
    CharacterSelection,
    Composition,
    LorebookSelection,
)


def test_invalid_targets_and_duplicate_primary():
    a, b = uuid4(), uuid4()
    invalid = [
        Composition((CharacterSelection(a, True), CharacterSelection(b, True))),
        Composition(
            (CharacterSelection(a),), (LorebookSelection(uuid4(), "selected", (b,)),)
        ),
        Composition((), (LorebookSelection(uuid4(), "selected"),)),
        Composition(
            (CharacterSelection(a),), (LorebookSelection(uuid4(), "all", (a,)),)
        ),
    ]
    for value in invalid:
        with pytest.raises(ValueError):
            validate(value)
