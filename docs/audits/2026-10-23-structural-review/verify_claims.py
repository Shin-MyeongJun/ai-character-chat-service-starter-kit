"""Reproduce selected audit claims with real functions and isolated test doubles.

Run from the repository root: .venv/Scripts/python.exe docs/audits/2026-10-23-structural-review/verify_claims.py
No database, credentials, or external network calls are used.
"""
from __future__ import annotations

import ast
import asyncio
import json
import io
import sys
import tempfile
import threading
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "apps/api"))

from app.modules.asset_storage.adapters.s3_storage.adapter import S3StorageAdapter
from app.modules.asset_storage.adapters.test_local_storage.adapter import TestLocalStorageAdapter
from app.modules.asset_storage.types import (ReadAssetCommand, S3StorageSettings, TestLocalStorageSettings,
    StoreAssetCommand, DeleteAssetCommand, AssetStorageError)
from app.modules.chatting.chat import types as ChatTypes
from app.modules.chatting.chat.service.workflow import answer_preparation as preparation
from app.modules.chatting.memory import types as MemoryTypes
from app.modules.chatting.memory.service.command.summarization import estimate_tokens, plan_summarization
from app.modules.content.character.service.workflow.media import _settle_storage
from app.modules.content.lorebook.service.activation import _matches, validate_options
from app.use_cases import studio_publication as publication


@asynccontextmanager
async def session_context(*_args):
    yield NS()


async def token_stall():
    messages = tuple(MemoryTypes.SourceMessageInfo(uuid4(), "user", "x" * 800, i + 1, 1) for i in range(11))
    cid, uid = uuid4(), uuid4()
    command = ChatTypes.PrepareAnswerContextCommand(
        conversation_id=cid, owner_id=uid, current_message=messages[-1].content,
        current_message_id=messages[-1].id, max_prompt_tokens=8000, response_tokens=1200,
        embedding_model="fake", runtime=NS(), rendered_base_tokens=1000,
    )
    with patch.object(preparation.MemoryService, "get_latest_summary", AsyncMock(return_value=None)), patch.object(
        preparation.MessagesQueryService, "list_memory_source", AsyncMock(return_value=ChatTypes.MemorySourceInfo(messages, False))
    ):
        try:
            await preparation.prepare_answer_context(session_context, command, memory_retriever=NS())
        except MemoryTypes.ContextBudgetExceededError as exc:
            summary_required = exc.summary_required
        else:
            summary_required = False
    plan = plan_summarization(MemoryTypes.PlanSummarizationCommand(
        conversation_id=cid, owner_id=uid, conversation_revision=1, messages=messages, policy=MemoryTypes.MemoryPolicy()
    ))
    assert summary_required and plan is None
    return {"summary_required": summary_required, "worker_plan": None,
            "rendered_history_cost": sum(preparation._rendered_message_tokens(m) for m in messages),
            "worker_history_cost": sum(estimate_tokens(f"{m.sender_type}: {m.content}\n") for m in messages),
            "available_history_budget": 5800, "worker_threshold": 4000}


async def cancellation_precedence():
    started, release = asyncio.Event(), asyncio.Event()
    async def provider():
        started.set()
        await release.wait()
        raise ValueError("simulated provider failure")
    caller = asyncio.create_task(_settle_storage(provider()))
    await started.wait()
    caller.cancel()
    await asyncio.sleep(0)  # deliver cancellation while the provider is still pending
    release.set()
    try:
        await caller
    except BaseException as exc:
        observed = type(exc).__name__
    assert observed == "ValueError"
    return {"after_caller_cancel_and_provider_failure": observed}


async def s3_cancelled_acquisition():
    loop = asyncio.get_running_loop()
    started, finished = asyncio.Event(), asyncio.Event()
    release = threading.Event()
    body = NS(closed=False)
    def close():
        body.closed = True
    body.close = close
    def get_object(**_kwargs):
        loop.call_soon_threadsafe(started.set)
        if not release.wait(timeout=5):
            raise RuntimeError("test synchronization timed out")
        loop.call_soon_threadsafe(finished.set)
        return {"Body": body}
    adapter = S3StorageAdapter(S3StorageSettings("audit", "fake-bucket", "fake-region"), client=NS(get_object=get_object))
    task = asyncio.create_task(adapter.read_asset(ReadAssetCommand("audit/object")))
    await asyncio.wait_for(started.wait(), 5)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    finally:
        release.set()
    await asyncio.wait_for(finished.wait(), 5)
    # Drain the executor and callbacks before checking ownership cleanup.
    await loop.run_in_executor(None, lambda: None)
    await asyncio.sleep(0)
    assert not body.closed
    observed = {"late_body_closed_by_adapter": body.closed, "provider": "injected fake client"}
    body.close()  # the audit harness owns cleanup of its own fake body
    return observed


def studio_document():
    return {"version": 2, "work": {"title": "Story", "introduction": "Intro", "visibility": "비공개", "defaultSceneId": "s", "worldRules": "Rules"},
            "characters": [{"id": "c", "name": "Hero", "persona": "Waits", "assets": [{"id": "a", "mediaId": str(uuid4()), "usage": 3}]}],
            "lorebooks": [], "scenes": [{"id": "s", "title": "Start", "characterId": "c", "opening": "Hello"}]}


async def malformed_studio_asset():
    document = studio_document()
    publication._publication_content(document)  # actual validator accepts usage: 3
    draft = NS(revision=1, document=document, content_digest="d", publication_digest=None, publication_release=None)
    command = publication.PublishStudioCommand(uuid4(), uuid4(), 1, uuid4(), "low", "Release", "Release body")
    mapping = {"characters": {}, "entries": {}, "receipts": {}}
    with patch.object(publication, "use_case_transaction", session_context), patch.object(
        publication, "get_studio_draft_for_publication", AsyncMock(return_value=draft)
    ), patch.object(publication, "component_mapping", AsyncMock(return_value=mapping)), patch.object(
        publication.CharacterCommand, "create_character", AsyncMock(return_value=NS(id=uuid4()))
    ):
        try:
            await publication.publish_studio(NS(), command)
        except TypeError as exc:
            error = str(exc)
        else:
            raise AssertionError("Expected invalid asset usage to reach a TypeError")
    return {"validator_accepted": True, "publish_error": error, "database_writes": "mocked"}


async def cursor_http_validation():
    from fastapi import FastAPI
    import httpx
    from app.modules.content.character.router import router as character_router
    from app.modules.content.lorebook.router import router as lorebook_router
    from app.http import character_dependencies as cd, lorebook_dependencies as ld
    app = FastAPI()
    app.include_router(character_router)
    app.include_router(lorebook_router)
    for dependency in (cd.get_character_session, ld.get_lorebook_session):
        app.dependency_overrides[dependency] = lambda: NS()
    for dependency in (cd.get_current_owner_id, ld.get_current_owner_id):
        app.dependency_overrides[dependency] = uuid4
    result = {}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://audit") as client:
        for path in ("/characters/me", "/lorebooks/me"):
            response = await client.get(path, params={"cursor_id": str(uuid4())})
            result[path] = response.status_code
            assert response.status_code == 422
    return {"incomplete_cursor_http_status": result, "database": "not used; auth/session replaced"}


async def local_open_reader_delete():
    with tempfile.TemporaryDirectory(prefix="audit-local-", dir=OUT) as directory:
        adapter = TestLocalStorageAdapter(TestLocalStorageSettings(root=Path(directory)))
        key = "audit/object"
        await adapter.store_asset(StoreAssetCommand(key, io.BytesIO(b"data"), 4, "application/octet-stream"))
        read = await adapter.read_asset(ReadAssetCommand(key))
        try:
            await adapter.delete_asset(DeleteAssetCommand(key))
        except AssetStorageError as exc:
            observed = {"error": type(exc).__name__, "kind": str(exc.kind), "cause": type(exc.__cause__).__name__}
        else:
            observed = {"error": None}
        finally:
            await read.aclose()
            await adapter.delete_asset(DeleteAssetCommand(key))
        for i in range(20):
            adapter._lock_for(f"audit/{i}")
        observed["retained_lock_keys"] = len(adapter._locks)
        return observed


def lore_options():
    options = validate_options({"activation_options": {"version": 1, "case_sensitive": True}})
    regex = _matches("abc", "ABC", "regex", options)
    exact = _matches("prefix ABC suffix", "ABC", "exact", options)
    assert regex and exact
    try:
        _matches("abc", "[", "regex", options)
    except Exception as exc:
        invalid = type(exc).__name__
    return {"regex_case_sensitive_true_matches_lowercase": regex, "exact_matches_substring": exact,
            "invalid_regex_exception": invalid, "exact_scope": "direct function; studio v1 normally emits contains"}


def inventory():
    files = sorted((ROOT / "apps/api/app").rglob("*.py"))
    empty = [str(p.relative_to(ROOT)).replace("\\", "/") for p in files if p.stat().st_size == 0 and p.name != "__init__.py"]
    short = [p for p in files if len(p.read_text(encoding="utf-8-sig").splitlines()) <= 15]
    forwarding, lock_calls, lock_keywords = [], 0, 0
    for p in files:
        tree = ast.parse(p.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "with_for_update":
                lock_calls += 1
            if isinstance(node, ast.Call):
                lock_keywords += sum(keyword.arg == "with_for_update" for keyword in node.keywords)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                body = node.body
                if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
                    body = body[1:]
                if len(body) == 1 and isinstance(body[0], ast.Return):
                    value = body[0].value
                    if isinstance(value, ast.Await):
                        value = value.value
                    if isinstance(value, ast.Call):
                        forwarding.append(f"{p.relative_to(ROOT).as_posix()}:{node.lineno}:{node.name}")
    tag_files = [ROOT / "apps/api/app/modules/content" / domain / tail
                 for domain in ("character", "lorebook", "product")
                 for tail in ("tag_router.py", "service/tags.py", "mapper/tags.py", "mapper/tag_schema.py")]
    return {"application_python_files": len(files), "files_at_most_15_lines_including_init": len(short),
            "empty_non_init_files": empty, "single_return_call_functions": len(forwarding),
            "single_return_call_definition": "sole non-docstring statement is return Call or return await Call; includes constructors and mappings, not necessarily pass-through",
            "with_for_update_method_calls": lock_calls, "with_for_update_keyword_arguments": lock_keywords,
            "tag_file_count": len(tag_files),
            "tag_physical_lines": sum(len(p.read_text(encoding="utf-8-sig").splitlines()) for p in tag_files),
            "forwarding_candidates": forwarding}


async def main():
    result = {"token_stall": await token_stall(), "cancellation_precedence": await cancellation_precedence(),
              "s3_cancelled_acquisition": await s3_cancelled_acquisition(),
              "malformed_studio_asset": await malformed_studio_asset(), "lore_options": lore_options(),
              "cursor_http_validation": await cursor_http_validation(),
              "local_open_reader_delete": await local_open_reader_delete(), "inventory": inventory()}
    (OUT / "verification-results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "inventory"}, ensure_ascii=False, indent=2))
    print(json.dumps({k: v for k, v in result["inventory"].items() if k != "forwarding_candidates"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
