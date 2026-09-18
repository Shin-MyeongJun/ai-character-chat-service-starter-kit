# 모듈 import/테이블 소유 경계와 기존 API 계약을 정적·OpenAPI 검사로 확인한다.
"""Contracts that must survive internal backend restructuring."""

import ast
import importlib
import json
from pathlib import Path

from fastapi import FastAPI

MODULES = Path(__file__).parents[1] / "app" / "modules"
USE_CASES = Path(__file__).parents[1] / "app" / "use_cases"


def test_openapi_contract_is_unchanged():
    app = FastAPI()
    for path in sorted(MODULES.rglob("*router.py")):
        name = ".".join(path.relative_to(MODULES.parent.parent).with_suffix("").parts)
        router = getattr(importlib.import_module(name), "router", None)
        if router is not None:
            app.include_router(router)
    baseline = json.loads(
        (Path(__file__).parent / "fixtures" / "backend-openapi.json").read_text(
            encoding="utf-8"
        )
    )
    # 신규 인증 API만 추가를 허용하고 기존 경로·스키마 계약은 그대로 비교한다.
    actual = app.openapi()
    assert set(actual["paths"]) - set(baseline["paths"]) == {
        "/auth/csrf",
        "/auth/register",
        "/auth/email/resend",
        "/auth/email/verify",
        "/auth/password/reset/request",
        "/auth/password/reset",
        "/auth/login",
        "/auth/refresh",
        "/auth/logout",
        "/auth/logout-all",
        "/auth/me",
        "/auth/google/start",
        "/auth/google/callback",
    }
    for path, contract in baseline["paths"].items():
        assert actual["paths"][path] == contract
    for name, schema in baseline["components"]["schemas"].items():
        assert actual["components"]["schemas"][name] == schema


def test_services_and_routers_do_not_execute_sql_or_import_orm():
    violations = []
    for path in MODULES.rglob("*.py"):
        if "service" not in path.parts and "router" not in path.stem:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module.startswith("app.db.models") or module == "sqlalchemy":
                    violations.append(f"{path}:{node.lineno}: {module}")
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in {"session", "db"}
                and node.func.attr
                in {
                    "execute",
                    "scalar",
                    "scalars",
                    "add",
                    "delete",
                    "commit",
                    "rollback",
                }
            ):
                violations.append(f"{path}:{node.lineno}: {node.func.attr}")
    assert not violations, "\n".join(violations)


def _module_owner(parts):
    parts = parts[parts.index("modules") + 1 :]
    length = 2 if parts[0] in {"content", "chatting", "commerce", "governance"} else 1
    return tuple(parts[:length])


def test_cross_module_imports_use_only_public_services_and_types():
    violations = []
    for path in MODULES.rglob("*.py"):
        own = _module_owner(["modules", *path.relative_to(MODULES).parts])
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.ImportFrom) or not node.module:
                continue
            if not node.module.startswith("app.modules."):
                continue
            for alias in node.names:
                parts = (node.module + "." + alias.name).split(".")
                other = _module_owner(parts)
                tail = parts[2 + len(other) :]
                if own != other and (not tail or tail[0] not in {"service", "types"}):
                    violations.append(f"{path}:{node.lineno}: {'.'.join(parts)}")
    assert not violations, "\n".join(violations)


def test_top_level_use_cases_use_only_public_module_services_and_types():
    violations = []
    for path in USE_CASES.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or not node.module:
                continue
            if node.module.startswith("app.db.models"):
                violations.append(f"{path}:{node.lineno}: {node.module}")
            if not node.module.startswith("app.modules."):
                continue
            for alias in node.names:
                parts = (node.module + "." + alias.name).split(".")
                domain_length = (
                    2
                    if parts[2] in {"content", "chatting", "commerce", "governance"}
                    else 1
                )
                tail = parts[2 + domain_length :]
                if not tail or tail[0] not in {"service", "types"}:
                    violations.append(f"{path}:{node.lineno}: {'.'.join(parts)}")
    assert not violations, "\n".join(violations)


def test_public_service_business_inputs_use_commands_and_declare_results():
    violations = []
    for path in MODULES.rglob("*.py"):
        if "service" not in path.parts:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.AsyncFunctionDef) or node.name.startswith("_"):
                continue
            if node.name == "aclose":  # Adapter resource lifetime, not a use case.
                continue
            business_args = [
                arg
                for arg in node.args.args + node.args.kwonlyargs
                if arg.arg
                not in {"self", "session", "embedding_service", "embed_query", "now"}
            ]
            if (
                any(
                    arg.annotation is None
                    or "Command" not in ast.unparse(arg.annotation)
                    for arg in business_args
                )
                or node.returns is None
            ):
                violations.append(f"{path}:{node.lineno}: {node.name}")
    assert not violations, "\n".join(violations)


def test_mappers_do_not_call_external_io_or_generate_values():
    violations = []
    for path in MODULES.rglob("*.py"):
        if "mapper" not in path.parts:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Await):
                violations.append(f"{path}:{node.lineno}: await")
            if isinstance(node, ast.Call):
                name = ast.unparse(node.func)
                if name.rsplit(".", 1)[-1] in {
                    "now",
                    "utcnow",
                    "uuid4",
                    "commit",
                    "flush",
                    "execute",
                }:
                    violations.append(f"{path}:{node.lineno}: {name}")
    assert not violations, "\n".join(violations)


def test_assembled_routes_preserve_the_same_openapi_contract():
    from app.http.routes import router

    app = FastAPI()
    app.include_router(router)
    baseline = json.loads(
        (Path(__file__).parent / "fixtures" / "backend-openapi.json").read_text(
            encoding="utf-8"
        )
    )
    actual = app.openapi()
    assert set(actual["paths"]) - set(baseline["paths"]) == {
        "/conversations/{conversation_id}/answers",
        "/characters/{character_id}/media/uploads",
        "/characters/media/{media_id}/content",
        "/products/{product_id}/versions/{snapshot_id}/media/{media_id}/content",
    }
    for path, contract in baseline["paths"].items():
        assert actual["paths"][path] == contract
    for name, schema in baseline["components"]["schemas"].items():
        assert actual["components"]["schemas"][name] == schema
