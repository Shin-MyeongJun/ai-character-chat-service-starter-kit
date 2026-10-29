"""Regression checks for the signature ratchet, independent of application imports."""

import importlib.util
import json
from pathlib import Path


def _checker():
    path = Path(__file__).parents[3] / "tools/check_backend_patterns.py"
    spec = importlib.util.spec_from_file_location("backend_pattern_checks", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_signature_rules_cover_private_sync_async_and_quoted_annotations():
    findings = _checker().collect_source(
        """
class Worker:
    def __init__(self, factory): pass
    async def _run(self, value: "dict", *, more) -> "list": pass
def sync(value: "typing.Any") -> None: pass
""",
        "sample.py",
    )
    assert findings == {
        "sample.py::Worker.__init__::factory::missing",
        "sample.py::Worker.__init__::return::missing",
        "sample.py::Worker._run::value::bare-dict",
        "sample.py::Worker._run::more::missing",
        "sample.py::Worker._run::return::bare-list",
        "sample.py::sync::value::explicit-any",
    }


def test_nested_callable_types_are_checked_but_literal_and_metadata_are_not():
    findings = _checker().collect_source(
        """
def run(callback: Callable[[dict], list[str]], mode: Literal["dict", "Any"],
        value: Annotated[str, "dict"]) -> tuple[str, ...]: pass
""",
        "sample.py",
    )
    assert findings == {"sample.py::run::callback::bare-dict"}


def test_ids_survive_formatting_but_distinguish_new_functions_and_scopes():
    collect = _checker().collect_source
    before = collect("def first(value): pass\n", "sample.py")
    assert collect("\n\ndef first(\n    value,\n):\n    pass\n", "sample.py") == before
    after = collect(
        "def first(value: int) -> None: pass\ndef second(value): pass\n", "sample.py"
    )
    assert len(before) == len(after)
    assert after - before  # A count-only baseline would incorrectly allow this.
    nested = collect(
        "class A:\n def run(self):\n  def helper(self): pass\n", "sample.py"
    )
    assert "sample.py::A.run.helper::self::missing" in nested


def test_prune_refuses_new_violations_without_modifying_baseline(tmp_path, monkeypatch):
    checker = _checker()
    baseline = tmp_path / "baseline.json"
    original = json.dumps({"violations": ["old"]})
    baseline.write_text(original, encoding="utf-8")
    monkeypatch.setattr(checker, "BASELINE", baseline)
    monkeypatch.setattr(checker, "collect", lambda: {"new"})
    monkeypatch.setattr("sys.argv", ["check", "--prune-baseline"])
    assert checker.main() == 1
    assert baseline.read_text(encoding="utf-8") == original


def test_prune_removes_resolved_entries_and_preserves_reason(tmp_path, monkeypatch):
    checker = _checker()
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps({"reason": "legacy debt", "violations": ["fixed", "remaining"]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(checker, "BASELINE", baseline)
    monkeypatch.setattr(checker, "collect", lambda: {"remaining"})
    monkeypatch.setattr("sys.argv", ["check", "--prune-baseline"])
    assert checker.main() == 0
    assert json.loads(baseline.read_text(encoding="utf-8")) == {
        "reason": "legacy debt",
        "violations": ["remaining"],
    }
