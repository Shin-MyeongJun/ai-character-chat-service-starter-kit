from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from app.modules.llm.replacement import choose_replacement, closest_effort


def model(provider, family, efforts=("low", "high")):
    return SimpleNamespace(
        id=uuid4(),
        provider_id=provider,
        is_enabled=True,
        shutdown_at=None,
        capabilities={"model_family": family, "reasoning_efforts": efforts},
    )


def test_same_family_preferred_and_allowlist_never_bypassed():
    p = uuid4()
    original = model(p, "a")
    sibling = model(p, "a")
    other = model(p, "b")
    choice = choose_replacement(
        original,
        [other, sibling],
        {"scope": "same_provider"},
        "medium",
        now=datetime.now(UTC),
    )
    assert choice == (sibling, "low")
    assert (
        choose_replacement(
            original,
            [sibling],
            {"scope": "allowlist", "model_ids": [str(other.id)]},
            "high",
            now=datetime.now(UTC),
        )
        is None
    )


def test_unknown_effort_is_not_guessed():
    assert closest_effort("unknown", ["high"]) is None
    assert closest_effort("high", []) is None
