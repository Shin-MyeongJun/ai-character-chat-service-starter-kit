"""Ratchet signature typing debt without importing application code or touching DBs."""

from __future__ import annotations

import argparse
import ast
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "tools/backend-pattern-baseline.json"
BARE_GENERICS = {
    "Callable",
    "dict",
    "list",
    "tuple",
    "set",
    "frozenset",
    "type",
    "Dict",
    "List",
    "Tuple",
    "Set",
    "FrozenSet",
    "Type",
    "Mapping",
    "MutableMapping",
    "Sequence",
    "Iterable",
    "Iterator",
    "AsyncIterator",
    "Awaitable",
    "Coroutine",
    "Collection",
    "AbstractAsyncContextManager",
}


def annotation_issues(node: ast.AST) -> set[str]:
    """Inspect annotations (including quoted references), not Literal string values."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        try:
            return annotation_issues(ast.parse(node.value, mode="eval").body)
        except SyntaxError:
            return {"invalid-forward-annotation"}
    if isinstance(node, ast.Subscript):
        base = ast.unparse(node.value).rsplit(".", 1)[-1]
        if base == "Literal":
            return set()
        if base == "Annotated" and isinstance(node.slice, ast.Tuple):
            return annotation_issues(node.slice.elts[0])
        return annotation_issues(node.slice)
    if isinstance(node, (ast.Name, ast.Attribute)):
        name = node.id if isinstance(node, ast.Name) else node.attr
        if name == "Any":
            return {"explicit-any"}
        if name in BARE_GENERICS:
            return {f"bare-{name}"}
        return set()
    return set().union(
        *(annotation_issues(child) for child in ast.iter_child_nodes(node))
    )


def collect_source(source: str, path: str) -> set[str]:
    """IDs use lexical names, not line numbers: formatting cannot reset the debt."""
    issues: set[str] = set()

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.scope: list[str] = []
            self.class_scope = False

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            self.scope.append(node.name)
            previous = self.class_scope
            self.class_scope = True
            for statement in node.body:
                self.visit(statement)
            self.class_scope = previous
            self.scope.pop()

        def visit_FunctionDef(
            self, node: ast.FunctionDef | ast.AsyncFunctionDef
        ) -> None:
            symbol = ".".join([*self.scope, node.name])
            args = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
            args += [arg for arg in (node.args.vararg, node.args.kwarg) if arg]
            for index, arg in enumerate(args):
                if self.class_scope and index == 0 and arg.arg in {"self", "cls"}:
                    continue
                self.check(arg.annotation, symbol, arg.arg)
            self.check(node.returns, symbol, "return")
            self.scope.append(node.name)
            previous = self.class_scope
            self.class_scope = False
            for statement in node.body:
                self.visit(statement)
            self.class_scope = previous
            self.scope.pop()

        visit_AsyncFunctionDef = visit_FunctionDef

        def check(self, annotation: ast.AST | None, symbol: str, slot: str) -> None:
            rules = {"missing"} if annotation is None else annotation_issues(annotation)
            for rule in rules:
                issues.add(f"{path}::{symbol}::{slot}::{rule}")

    Visitor().visit(ast.parse(source))
    return issues


def collect(root: Path = ROOT) -> set[str]:
    issues: set[str] = set()
    for path in sorted((root / "apps/api/app").rglob("*.py")):
        issues.update(
            collect_source(
                path.read_text(encoding="utf-8-sig"), path.relative_to(root).as_posix()
            )
        )
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--inventory",
        action="store_true",
        help="Print current findings as JSON; do not modify the baseline",
    )
    parser.add_argument(
        "--prune-baseline",
        action="store_true",
        help="Remove resolved entries only; new entries are never accepted",
    )
    args = parser.parse_args()
    current = collect()
    if args.inventory:
        print(
            json.dumps(
                {
                    "count": len(current),
                    "rules": dict(
                        Counter(item.rsplit("::", 1)[-1] for item in sorted(current))
                    ),
                    "violations": sorted(current),
                },
                indent=2,
            )
        )
        return 0
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    recorded = set(baseline["violations"])
    added, resolved = current - recorded, recorded - current
    if added:
        print(
            "New backend signature violations (fix the code; do not expand baseline):"
        )
        print("\n".join(sorted(added)))
        return 1
    if resolved and args.prune_baseline:
        baseline["violations"] = sorted(current)
        BASELINE.write_text(json.dumps(baseline, indent=2) + "\n", encoding="utf-8")
    elif resolved:
        print(f"{len(resolved)} resolved entries; run --prune-baseline to remove them.")
        return 1
    print(
        f"Signature ratchet passed: {len(current)} known findings; no new violations."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
