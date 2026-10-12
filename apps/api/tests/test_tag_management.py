"""Tag service policies and HTTP boundaries without a PostgreSQL dependency."""

import importlib
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.modules.content.tag import types as TagTypes
from app.modules.content.tag.service import command as TagCommandService
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture(params=("product", "character", "lorebook"))
def domain(request, monkeypatch):
    name = request.param
    service = importlib.import_module(f"app.modules.content.{name}.service.tags")
    types = importlib.import_module(f"app.modules.content.{name}.types")
    owner, admin, target = uuid4(), uuid4(), uuid4()
    content = SimpleNamespace(owner_id=owner, status="draft", visibility="private")
    public, internal, dictionary = {}, {}, {}
    clock = datetime.now(UTC)

    async def get_target(*args, **kwargs):
        return content

    monkeypatch.setattr(service, "_get_tag_target", AsyncMock(side_effect=get_target))

    async def require_admin(session, command):
        if command.user_id != admin:
            raise LookupError("Administrative operation unavailable.")

    monkeypatch.setattr(
        service.IdentityQueryService,
        "require_admin",
        AsyncMock(side_effect=require_admin),
    )
    calls = []

    async def resolve(session, tag_name, description=None):
        calls.append(tag_name)
        if tag_name not in dictionary:
            dictionary[tag_name] = SimpleNamespace(
                id=uuid4(), name=tag_name, is_active=True, description=description
            )
        return dictionary[tag_name]

    monkeypatch.setattr(TagCommandService.Repository, "resolve_tag", resolve)

    async def get_tags(session, command):
        return tuple(
            TagTypes.TagInfo(t.id, t.name, t.description, t.is_active)
            for t in dictionary.values()
            if t.id in command.tag_ids
        )

    monkeypatch.setattr(service.TagQueryService, "get_tags", get_tags)

    async def public_links(*args):
        return sorted(public.values(), key=lambda row: row.sort_order)

    async def internal_links(*args):
        return list(internal.values())

    async def replace_public(session, target_id, ids, actor):
        for old in set(public) - set(ids):
            del public[old]
        for order, tid in enumerate(ids):
            if tid not in public:
                public[tid] = SimpleNamespace(
                    tag_id=tid, assigned_by=actor, created_at=clock
                )
            public[tid].sort_order = order

    async def remove_public(session, target_id, tag_id):
        public.pop(tag_id, None)

    async def set_internal(session, target_id, tag_id, source, actor):
        internal[tag_id] = SimpleNamespace(
            tag_id=tag_id,
            source=source,
            assigned_by=actor,
            created_at=clock,
            updated_at=clock,
        )

    async def remove_internal(session, target_id, tag_ids):
        for tid in tag_ids:
            internal.pop(tid, None)

    repo = service.Repository
    monkeypatch.setattr(repo, "list_public_tag_links", public_links)
    monkeypatch.setattr(repo, "list_internal_tag_links", internal_links)
    monkeypatch.setattr(repo, "replace_public_tag_links", replace_public)
    monkeypatch.setattr(repo, "remove_public_tag_link", remove_public)
    monkeypatch.setattr(repo, "set_internal_tag_link", set_internal)
    monkeypatch.setattr(repo, "remove_internal_tag_links", remove_internal)
    return SimpleNamespace(
        name=name,
        service=service,
        types=types,
        owner=owner,
        admin=admin,
        target=target,
        content=content,
        public=public,
        internal=internal,
        dictionary=dictionary,
        calls=calls,
    )


@pytest.mark.asyncio
async def test_public_order_exact_names_reuse_inactive_retention_and_clear(domain):
    d = domain
    async with AsyncSession() as session:
        result = await d.service.add_public_tags(
            session,
            d.types.PublicTagsCommand(
                d.target, d.owner, (" Z ", "A", "Z", "a", "현대  판타지")
            ),
        )
        assert [t.name for t in result] == ["Z", "A", "a", "현대  판타지"]
        assert d.calls == sorted({"Z", "A", "a", "현대  판타지"})
        assert all(row.assigned_by == d.owner for row in d.public.values())
        d.dictionary["Z"].is_active = False
        result = await d.service.replace_public_tags(
            session, d.types.PublicTagsCommand(d.target, d.owner, ("A", "Z"))
        )
        assert [(t.name, t.sort_order) for t in result] == [("A", 0), ("Z", 1)]
        assert result[1].is_active is False
        await d.service.remove_public_tag(
            session, d.types.PublicTagsCommand(d.target, d.owner, tag_id=result[1].id)
        )
        with pytest.raises(ValueError, match="Inactive"):
            await d.service.add_public_tags(
                session, d.types.PublicTagsCommand(d.target, d.owner, ("Z",))
            )
        assert len(d.public) == 1
        result = await d.service.replace_public_tags(
            session, d.types.PublicTagsCommand(d.target, d.owner, ())
        )
        assert result == ()
        assert set(d.dictionary) == {"Z", "A", "a", "현대  판타지"}


@pytest.mark.asyncio
async def test_public_owner_access_and_invalid_names_rollback(domain):
    d = domain
    async with AsyncSession() as session:
        events = []
        event.listen(
            session.sync_session, "after_rollback", lambda _: events.append("rollback")
        )
        with pytest.raises(LookupError):
            await d.service.add_public_tags(
                session, d.types.PublicTagsCommand(d.target, uuid4(), ("forged",))
            )
        assert not d.dictionary
        for names in ((" ",), (123,), "not-a-list"):
            with pytest.raises(ValueError):
                await d.service.add_public_tags(
                    session, d.types.PublicTagsCommand(d.target, d.owner, names)
                )
        assert len(events) == 4
        assert not session.in_transaction()
        with pytest.raises(LookupError):
            await d.service.list_public_tags(
                session, d.types.PublicTagsCommand(d.target, uuid4())
            )
        d.service._get_tag_target.assert_called_with(session, d.target)


@pytest.mark.asyncio
async def test_internal_admin_system_protection_and_no_public_leak(domain):
    d = domain
    async with AsyncSession() as session:
        with pytest.raises(LookupError):
            await d.service.add_internal_tags(
                session,
                d.types.InternalTagsCommand(d.target, d.owner, ("private-interest",)),
            )
        result = await d.service.add_internal_tags(
            session,
            d.types.InternalTagsCommand(d.target, d.admin, ("private-interest",)),
        )
        tid = result[0].id
        assert result[0].source == "admin" and result[0].assigned_by == d.admin
        result = await d.service.set_system_tags(
            session,
            d.types.SystemTagsCommand(d.target, ("private-interest", "inferred")),
        )
        by_name = {t.name: t for t in result}
        assert by_name["private-interest"].source == "admin"
        assert by_name["inferred"].source == "system"
        assert by_name["inferred"].assigned_by is None
        with pytest.raises(ValueError, match="administrator"):
            await d.service.remove_system_tag(
                session, d.types.SystemTagsCommand(d.target, tag_id=tid)
            )
        assert (
            await d.service.list_public_tags(
                session, d.types.PublicTagsCommand(d.target, d.owner)
            )
            == ()
        )
        result = await d.service.replace_internal_tags(
            session, d.types.InternalTagsCommand(d.target, d.admin, ("inferred",))
        )
        assert len(result) == 1 and result[0].source == "admin"
        await d.service.remove_internal_tag(
            session, d.types.InternalTagsCommand(d.target, d.admin, tag_id=result[0].id)
        )
        assert not d.internal
        assert len(d.dictionary) == 2


@pytest.mark.asyncio
async def test_failure_of_tag_linking_rolls_back_content_creation(monkeypatch):
    from app.modules.content.character import types
    from app.modules.content.character.service import command, tags

    entity = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(
        command.Repository, "create_character_command", AsyncMock(return_value=object())
    )
    monkeypatch.setattr(
        command.PersistenceMapper, "character_entity_to_info", lambda row: entity
    )
    failure = AsyncMock(side_effect=ValueError("invalid tag"))
    monkeypatch.setattr(tags, "replace_public_tags", failure)
    async with AsyncSession() as session:
        events = []
        event.listen(
            session.sync_session, "after_commit", lambda _: events.append("commit")
        )
        event.listen(
            session.sync_session, "after_rollback", lambda _: events.append("rollback")
        )
        with pytest.raises(ValueError):
            await command.create_character(
                session,
                types.CreateCharacterCommand(uuid4(), "name", "persona", tags=("bad",)),
            )
        assert events == ["rollback"]
        assert not session.in_transaction()


def test_creation_contracts_accept_optional_tags_and_preserve_trusted_owner():
    for domain in ("character", "lorebook"):
        schemas = importlib.import_module(f"app.http.contracts.{domain}")
        mapper = importlib.import_module(f"app.modules.content.{domain}.mapper.schema")
        cl = domain.title()
        payload = (
            {"name": "name", "persona_prompt": "persona"}
            if domain == "character"
            else {"title": "title"}
        )
        dto = getattr(schemas, "Create" + cl + "RequestDto")(**payload)
        assert dto.tags == []
        dto = getattr(schemas, "Create" + cl + "RequestDto")(
            **payload, tags=[" A ", "A"]
        )
        owner = uuid4()
        result = getattr(
            getattr(mapper, cl + "SchemaMapper"),
            "create_" + domain + "_request_to_command",
        )(dto, owner)
        assert result.tags == (" A ", "A") and result.owner_id == owner


def test_http_routes_trust_actor_and_reject_source_spoofing(monkeypatch):
    from app.http.dependencies import get_current_owner_id, get_product_session
    from app.http.routes import router
    from app.modules.content.product.service import tags
    from app.modules.governance.admin.tag_router import ProductTagsService

    owner = uuid4()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_owner_id] = lambda: owner
    app.dependency_overrides[get_product_session] = lambda: object()
    public = AsyncMock(return_value=())
    internal = AsyncMock(return_value=())
    monkeypatch.setattr(tags, "add_public_tags", public)
    monkeypatch.setattr(ProductTagsService, "add_internal_tags", internal)
    with TestClient(app) as client:
        pid = uuid4()
        assert (
            client.post(f"/products/{pid}/tags", json={"tags": ["Fantasy"]}).status_code
            == 200
        )
        assert public.call_args.args[1].user_id == owner
        assert (
            client.post(
                f"/products/{pid}/tags",
                json={"tags": ["Fantasy"], "assigned_by": str(uuid4())},
            ).status_code
            == 422
        )
        assert (
            client.post(
                f"/admin/products/{pid}/internal-tags",
                json={"tags": ["interest"], "source": "system"},
            ).status_code
            == 422
        )
        assert (
            client.post(
                f"/admin/products/{pid}/internal-tags", json={"tags": ["interest"]}
            ).status_code
            == 200
        )
        assert internal.call_args.args[1].actor_id == owner
        assert "/tags" not in app.openapi()["paths"]
        fields = app.openapi()["components"]["schemas"]["PublicTagResponseDto"][
            "properties"
        ]
        assert "source" not in fields and "assigned_by" not in fields


@pytest.mark.asyncio
async def test_dictionary_admin_crud_reuses_names_and_restricts_management(
    domain, monkeypatch
):
    from app.modules.content.tag.service import query as TagQueryService

    d = domain

    async def get_tag(session, tag_id, **kwargs):
        return next((row for row in d.dictionary.values() if row.id == tag_id), None)

    async def get_by_name(session, name):
        return d.dictionary.get(name)

    async def update_tag(session, tag_id, name, description):
        row = await get_tag(session, tag_id)
        d.dictionary.pop(row.name)
        row.name = name
        row.description = description
        d.dictionary[name] = row
        return row

    async def deactivate(session, tag_id):
        row = await get_tag(session, tag_id)
        row.is_active = False
        return row

    monkeypatch.setattr(TagCommandService.Repository, "get_tag", get_tag)
    monkeypatch.setattr(TagCommandService.Repository, "get_tag_by_name", get_by_name)
    monkeypatch.setattr(TagCommandService.Repository, "update_tag", update_tag)
    monkeypatch.setattr(TagCommandService.Repository, "deactivate_tag", deactivate)
    async with AsyncSession() as session:
        with pytest.raises(LookupError):
            await TagCommandService.create_tag(
                session, TagTypes.CreateTagCommand(d.owner, "x")
            )
        original = await TagCommandService.create_tag(
            session, TagTypes.CreateTagCommand(d.admin, " x ", "original")
        )
        same = await TagCommandService.create_tag(
            session, TagTypes.CreateTagCommand(d.admin, "x", "overwrite")
        )
        assert same.id == original.id and same.description == "original"
        exact = await TagQueryService.get_tag_by_name(
            session, TagTypes.GetTagByNameCommand(" x ")
        )
        assert exact.id == original.id
        assert (
            await TagQueryService.get_tag_by_name(
                session, TagTypes.GetTagByNameCommand("X")
            )
            is None
        )
        renamed = await TagCommandService.update_tag(
            session,
            TagTypes.UpdateTagCommand(original.id, d.admin, "renamed", "edited"),
        )
        assert renamed.id == original.id and renamed.name == "renamed"
        inactive = await TagCommandService.deactivate_tag(
            session, TagTypes.DeactivateTagCommand(original.id, d.admin)
        )
        assert not inactive.is_active and "renamed" in d.dictionary
        with pytest.raises(LookupError):
            await TagCommandService.update_tag(
                session, TagTypes.UpdateTagCommand(original.id, d.owner, "forged")
            )
