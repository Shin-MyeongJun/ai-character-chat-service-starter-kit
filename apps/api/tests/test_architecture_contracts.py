# 모듈 import/테이블 소유 경계와 기존 API 계약을 정적·OpenAPI 검사로 확인한다.
"""Contracts that must survive internal backend restructuring."""

import ast
import json
from pathlib import Path

from app.main import create_app

MODULES = Path(__file__).parents[1] / "app" / "modules"
USE_CASES = Path(__file__).parents[1] / "app" / "use_cases"


TAG_PATHS = {
    "/characters/me/{target_id}/tags", "/characters/me/{target_id}/tags/{tag_id}",
    "/lorebooks/me/{target_id}/tags", "/lorebooks/me/{target_id}/tags/{tag_id}",
    "/products/{target_id}/tags", "/products/{target_id}/tags/{tag_id}",
    "/admin/products/{target_id}/internal-tags", "/admin/products/{target_id}/internal-tags/{tag_id}",
    "/admin/characters/{target_id}/internal-tags", "/admin/characters/{target_id}/internal-tags/{tag_id}",
    "/admin/lorebooks/{target_id}/internal-tags", "/admin/lorebooks/{target_id}/internal-tags/{tag_id}",
    "/admin/tags", "/admin/tags/{tag_id}",
}

PROMPT_REPORT_PATHS = {
    "/admin/reporting/generation-prompts",
    "/admin/reporting/generation-prompts/{generation_id}",
}


def _assert_existing_schema(name, actual, baseline):
    if name in {"CreateCharacterRequestDto", "CreateLorebookRequestDto", "ProductWriteRequestDto"}:
        actual = {**actual, "properties": dict(actual["properties"])}
        assert "tags" in actual["properties"]
        assert "tags" not in actual.get("required", [])
        actual["properties"].pop("tags")
    additions = {"ProductInfoResponseDto": {"has_publication"}, "ListProductsRequestDto": {"search"}, "GenerateAnswerRequestDto": {"manual_entry_ids"}}
    if name in additions:
        actual = {**actual, "properties": dict(actual["properties"])}
        for field in additions[name]:
            assert field in actual["properties"] and field not in actual.get("required", [])
            actual["properties"].pop(field)
    assert actual == baseline


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
    length = 2 if parts[0] in {"content", "chatting", "commerce", "governance", "reporting"} else 1
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


def test_credit_ownership_and_dependency_direction():
    violations = []
    owners = {
        "CreditAccount": ("commerce", "credit"),
        "CreditWallet": ("commerce", "credit"),
        "CreditBalance": ("commerce", "credit"),
        "CreditTransactionEntry": ("commerce", "credit"),
        "CreditTransaction": ("commerce", "credit"),
        "CreditReservation": ("commerce", "credit"),
        "BillingQuote": ("commerce", "billing"),
        "BillingCreditBinding": ("commerce", "billing"),
    }
    for path in MODULES.rglob("*.py"):
        own = _module_owner(["modules", *path.relative_to(MODULES).parts])
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            imports = []
            if isinstance(node, ast.ImportFrom):
                imports = [node.module or ""]
                if (node.module or "").startswith("app.db.models"):
                    for alias in node.names:
                        if alias.name in owners and own != owners[alias.name]:
                            violations.append(
                                f"{path}:{node.lineno}: foreign ORM {alias.name}"
                            )
                    if (
                        own == ("commerce", "credit")
                        and node.module != "app.db.models.credit"
                    ):
                        violations.append(
                            f"{path}:{node.lineno}: credit imports foreign models"
                        )
            elif isinstance(node, ast.Import):
                imports = [alias.name for alias in node.names]
                if any(name.startswith("app.db.models") for name in imports):
                    violations.append(
                        f"{path}:{node.lineno}: use explicit owned ORM imports"
                    )
            for imported in imports:
                if own == ("commerce", "credit") and imported.startswith(
                    ("app.modules.commerce.billing", "app.modules.chatting")
                ):
                    violations.append(
                        f"{path}:{node.lineno}: reverse credit dependency"
                    )
                if own[0] == "chatting" and imported.startswith(
                    "app.modules.commerce.credit"
                ):
                    violations.append(
                        f"{path}:{node.lineno}: direct chat-to-credit dependency"
                    )
            if (
                own == ("commerce", "credit")
                and isinstance(node, ast.Constant)
                and isinstance(node.value, str)
            ):
                if (
                    node.value in {"chat_usage", "billing_quotes", "quote_id"}
                    or "billing:credit-settlement:" in node.value
                ):
                    violations.append(
                        f"{path}:{node.lineno}: billing meaning in credit"
                    )
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
                    if parts[2] in {"content", "chatting", "commerce", "governance", "reporting"}
                    else 1
                )
                tail = parts[2 + domain_length :]
                if not tail or tail[0] not in {"service", "types"}:
                    violations.append(f"{path}:{node.lineno}: {'.'.join(parts)}")
    assert not violations, "\n".join(violations)


def test_public_service_business_inputs_use_commands_and_declare_results():
    # Execution dependencies are scoped to exact functions and annotations.
    # Only session_factory may be positional; existing billing guards stay intact.
    execution_dependencies = {
        (
            "chatting/chat/service/workflow/answer_preparation.py",
            "prepare_answer_context",
        ): {
            "session_factory": "Callable",
            "memory_retriever": "MemoryService.MemoryRetriever",
        },
        ("chatting/chat/service/workflow/memory.py", "process_memory_work"): {
            "session_factory": "Callable",
            "summary_generator": "MemoryService.SummaryGenerator",
            "indexer": "MemoryService.MemoryIndexer",
        },
        ("commerce/billing/service/quotes.py", "create_billing_quote"): {
            "configuration": "PricingService.BillingPricingConfiguration",
            "clock": "Callable[[], datetime]",
        },
        ("commerce/billing/service/quotes.py", "get_billing_quote"): {
            "clock": "Callable[[], datetime]",
        },
        ("commerce/billing/service/quotes.py", "validate_billing_quote"): {
            "clock": "Callable[[], datetime]",
        },
        ("commerce/billing/service/credits.py", "reserve_credit"): {
            "clock": "Callable[[], datetime]",
        },
    }
    violations = []
    for path in MODULES.rglob("*.py"):
        if "service" not in path.parts:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.AsyncFunctionDef) or node.name.startswith("_"):
                continue
            if node.name == "aclose":  # Adapter resource lifetime, not a use case.
                continue
            dependencies = execution_dependencies.get(
                (path.relative_to(MODULES).as_posix(), node.name), {}
            )
            business_args = [
                arg
                for arg in node.args.args + node.args.kwonlyargs
                if arg.arg
                not in {"self", "session", "embedding_service", "embed_query", "now"}
                and not (
                    (arg in node.args.kwonlyargs or arg.arg == "session_factory")
                    and arg.annotation is not None
                    and dependencies.get(arg.arg) == ast.unparse(arg.annotation)
                )
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
    app = create_app()
    baseline = json.loads(
        (Path(__file__).parent / "fixtures" / "backend-openapi.json").read_text(
            encoding="utf-8"
        )
    )
    actual = app.openapi()
    assert TAG_PATHS <= set(actual["paths"])
    assert PROMPT_REPORT_PATHS <= set(actual["paths"])
    assert set(actual["paths"]) - set(baseline["paths"]) - TAG_PATHS - PROMPT_REPORT_PATHS == {
        "/products/catalog",
        "/products/catalog-tags",
        "/products/mine/count",
        "/conversations/{conversation_id}/manual-lore",
        "/products/{product_id}/studio-draft",
        "/conversations/mine",
        "/products/catalog/{product_id}",
        "/models/available",
        "/products/{product_id}/studio-publication",
        "/account/credits",
        "/account/overview-counts",
        "/products/{product_id}/studio-components",
        "/products/studio/lore-diagnostics",
        "/account/credits/transactions",
        "/conversations/{conversation_id}/answers",
        "/conversations/{conversation_id}/start",
        "/characters/{character_id}/media/uploads",
        "/characters/media/{media_id}/content",
        "/products/{product_id}/versions/{snapshot_id}/media/{media_id}/content",
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
        actual_contract = actual["paths"][path]
        if path == "/products/mine":
            actual_contract = {**actual_contract, "get": {**actual_contract["get"], "parameters": [item for item in actual_contract["get"]["parameters"] if item["name"] != "search"]}}
        if path == "/products/mine":
            actual_contract["get"].pop("description", None)
        assert actual_contract == contract
    for name, schema in baseline["components"]["schemas"].items():
        _assert_existing_schema(name, actual["components"]["schemas"][name], schema)


def test_workflow_direction_and_prompt_independence():
    violations = []
    for path in MODULES.rglob("*.py"):
        own = _module_owner(["modules", *path.relative_to(MODULES).parts])
        relative = path.relative_to(MODULES).as_posix()
        lower_service = any(
            part in path.parts for part in ("command", "query")
        ) or relative in {
            "identity/service/authentication.py",
            "identity/service/google.py",
            "content/character/service/media.py",
        }
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom):
                names = [(node.module or "") + "." + alias.name for alias in node.names]
            elif isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            else:
                continue
            for name in names:
                if ".service.workflow" in name and lower_service:
                    violations.append(f"{path}: lower service imports workflow {name}")
                if "workflow" in path.parts and (
                    "repository" in name or name.startswith("app.db.models")
                ):
                    violations.append(f"{path}: workflow bypasses services {name}")
                if own == ("chatting", "prompt") and name.startswith(
                    "app.modules.chatting.chat"
                ):
                    violations.append(f"{path}: prompt depends on chat {name}")
                if own == ("chatting", "prompt") and name.startswith(
                    (
                        "app.modules.chatting.conversation.service",
                        "app.modules.chatting.memory.service",
                    )
                ):
                    violations.append(
                        f"{path}: prompt collects context from services {name}"
                    )
                if own == ("chatting", "memory") and name.startswith(
                    "app.modules.chatting.chat"
                ):
                    violations.append(f"{path}: memory depends on chat {name}")
                if own == ("chatting", "conversation") and name.startswith(
                    "app.modules.chatting.chat"
                ):
                    violations.append(f"{path}: conversation depends on chat {name}")
                if name.startswith("app.use_cases.") and not (
                    path.relative_to(MODULES).as_posix()
                    == "content/product/statistics_job.py"
                    and name
                    in {
                        "app.use_cases.product_statistics.enqueue_recent",
                        "app.use_cases.product_statistics.process_pending",
                    }
                ):
                    violations.append(
                        f"{path}: module imports top-level use case {name}"
                    )
    assert not violations, "\n".join(violations)
