"""Contract assertions for independently identified candidates; no live suppliers."""

import asyncio
from copy import deepcopy
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.product import ProductStudioDraft
from app.db.models.snapshot.product import ProductSnapshot
from app.db.transaction import use_case_transaction
from app.modules.chatting.chat import types as ChatTypes
from app.modules.content.product import types as ProductTypes
from app.modules.content.tag import types as TagTypes
from app.modules.content.tag.service import command as TagCommand
from app.use_cases import studio_components as Components
from app.use_cases import studio_publication as Publication
from test_answer_billing_integration import check_state
from test_nonstream_answers import result, setup_answer
from test_product_integration import ready_product
from test_studio_publication import document


@pytest.mark.asyncio
@pytest.mark.parametrize("cause", ["deadline", "caller_cancel"])
@pytest.mark.parametrize("suppress_cancel", [True, False])
async def test_late_answer_must_not_be_saved_or_charged(db, cause, suppress_cancel):
    config = ChatTypes.AnswerConfig(timeout_seconds=0.5)
    orchestrator, command, provider = await setup_answer(db, config=config)
    entered, never = asyncio.Event(), asyncio.Event()
    cancellation_seen = False

    async def late_result(_):
        nonlocal cancellation_seen
        entered.set()
        try:
            await never.wait()
        except asyncio.CancelledError:
            cancellation_seen = True
            if not suppress_cancel:
                raise
            return result("synthetic audit result")

    provider.generate_text.side_effect = late_result
    task = asyncio.create_task(orchestrator.generate_answer(command))
    await asyncio.wait_for(entered.wait(), 10)
    if cause == "caller_cancel":
        task.cancel()
    try:
        answer = await asyncio.wait_for(task, 10)
    except asyncio.CancelledError:
        assert cause == "caller_cancel"
        await check_state(
            orchestrator, command, status="cancelled", balance=20, reserved=0, charge=0
        )
        print("CONTROL cooperative_cancel status=cancelled debit=0")
        return
    assert cancellation_seen
    if answer.status == "succeeded":
        await check_state(
            orchestrator, command, status="succeeded", balance=10, reserved=0, charge=10
        )
        print(f"OBSERVED late_answer cause={cause} cancellation_seen=True status=succeeded ai_messages=1 debit=10 reserved=0")
    else:
        await check_state(
            orchestrator, command, status="failed", balance=20, reserved=0, charge=0
        )
        print("CONTROL cooperative_deadline status=failed debit=0")
    assert answer.status != "succeeded", "Late cancelled provider result was saved and charged"


@pytest.mark.asyncio
@pytest.mark.parametrize("preexisting", [False, True])
async def test_two_studio_publications_must_not_deadlock_on_cross_component_tags(db, monkeypatch, preexisting):
    # Two real publication use cases, different products and sessions. Only an
    # execution barrier is injected AFTER production resolve SQL has completed.
    owner_info, _, _, _, model, _ = await ready_product(db)
    owner = owner_info.id
    if preexisting:
        await TagCommand.resolve_tags(db, TagTypes.ResolveTagsCommand(("audit-alpha", "audit-beta")))
    drafts = []
    for first, second in (("audit-alpha", "audit-beta"), ("audit-beta", "audit-alpha")):
        value = document()
        value["characters"][0]["tags"] = [first]
        value["lorebooks"][0]["tags"] = [second]
        drafts.append(await Components.save_studio(
            db, ProductTypes.SaveStudioDraftCommand(uuid4(), owner, None, value)
        ))
    barrier = asyncio.Barrier(2)
    resolve = TagCommand.resolve_tags
    pids = set()

    async def gated_resolve(session, command):
        infos = await resolve(session, command)
        if not session.info.get("audit_first_tags"):
            session.info["audit_first_tags"] = True
            await asyncio.wait_for(barrier.wait(), 5)
        return infos

    monkeypatch.setattr(TagCommand, "resolve_tags", gated_resolve)

    async def publish(draft):
        async with AsyncSession(db.bind, expire_on_commit=False) as session:
            try:
                async with use_case_transaction(session):
                    await session.execute(text("SET LOCAL statement_timeout = '8s'"))
                    await session.execute(text("SET LOCAL lock_timeout = '6s'"))
                    pids.add(await session.scalar(text("SELECT pg_backend_pid()")))
                    return await Publication.publish_studio(session, Publication.PublishStudioCommand(
                        draft.product_id, owner, draft.revision, model.id, "low", "Audit", "Audit"
                    ))
            except DBAPIError as exc:
                return getattr(exc.orig, "sqlstate", None)
            except Exception as exc:
                return type(exc).__name__

    outcomes = await asyncio.wait_for(asyncio.gather(*(publish(draft) for draft in drafts)), 15)
    assert len(pids) == 2
    labels = sorted(item if isinstance(item, str) else type(item).__name__ for item in outcomes)
    print(f"OBSERVED studio_publications preexisting={preexisting} separate_connections={len(pids)} outcomes={labels}")
    async with db.begin():
        snapshots = await db.scalar(select(func.count()).select_from(ProductSnapshot))
        saved_drafts = await db.scalar(select(func.count()).select_from(ProductStudioDraft))
    print(f"OBSERVED studio_rollback snapshots={snapshots} drafts_preserved={saved_drafts}")
    assert "40P01" not in outcomes, "Cross-component new tag insertion deadlocked real PostgreSQL"
    assert labels == ["ReleaseInfo", "ReleaseInfo"]


@pytest.mark.asyncio
async def test_noop_publication_retry_must_survive_later_draft_save(db):
    owner, _, _, _, model, _ = await ready_product(db)
    original = document()
    product_id = uuid4()
    first_draft = await Components.save_studio(db, ProductTypes.SaveStudioDraftCommand(
        product_id, owner.id, None, original
    ))
    first_command = Publication.PublishStudioCommand(
        product_id, owner.id, first_draft.revision, model.id, "low", "Audit", "Audit"
    )
    first_release = await Publication.publish_studio(db, first_command)
    async with db.begin():
        original_snapshot = deepcopy(await db.scalar(
            select(ProductSnapshot.snapshot_data).where(ProductSnapshot.id == first_release.snapshot_id)
        ))
    edited = deepcopy(original)
    edited["work"]["title"] = "Synthetic edit"
    second_draft = await Components.save_studio(db, ProductTypes.SaveStudioDraftCommand(
        product_id, owner.id, first_draft.revision, edited
    ))
    reverted = await Components.save_studio(db, ProductTypes.SaveStudioDraftCommand(
        product_id, owner.id, second_draft.revision, original
    ))
    retry_command = Publication.PublishStudioCommand(
        product_id, owner.id, reverted.revision, model.id, "low", "Audit", "Audit"
    )
    assert await Publication.publish_studio(db, retry_command) == first_release
    later = await Components.save_studio(db, ProductTypes.SaveStudioDraftCommand(
        product_id, owner.id, reverted.revision, edited
    ))
    receipt_keys = sorted(later.publication_release["_studio"]["receipts"])
    conflict = False
    try:
        retried = await Publication.publish_studio(db, retry_command)
    except ProductTypes.StudioDraftConflictError:
        conflict = True
        retried = None
    print(f"OBSERVED noop_publication accepted_revision={reverted.revision} later_revision={later.revision} receipt_revisions={receipt_keys} same_request_conflict={conflict}")
    async with db.begin():
        snapshot_count = await db.scalar(select(func.count()).select_from(ProductSnapshot))
        current_snapshot = await db.scalar(
            select(ProductSnapshot.snapshot_data).where(ProductSnapshot.id == first_release.snapshot_id)
        )
    assert original_snapshot == current_snapshot
    print(f"OBSERVED noop_publication snapshots={snapshot_count} old_snapshot_preserved={original_snapshot == current_snapshot}")
    assert retried == first_release, "Accepted no-op publication lost its retry receipt after a later save"
