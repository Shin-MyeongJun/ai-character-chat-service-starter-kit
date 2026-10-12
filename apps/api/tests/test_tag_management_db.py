"""PostgreSQL-only concurrency and atomic content/tag persistence checks."""

import asyncio
import importlib
import os
from uuid import uuid4

import pytest
from app.db.transaction import use_case_transaction
from app.modules.content.tag import types as TagTypes
from app.modules.content.tag.service import command as TagCommandService
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not os.getenv("TEST_DATABASE_URL"),
        reason="TEST_DATABASE_URL required for PostgreSQL integration tests",
    ),
]


def create_command(domain, owner, tags):
    types = importlib.import_module(f"app.modules.content.{domain}.types")
    if domain == "product":
        return types.CreateProductCommand(
            owner_id=owner, value=types.ProductProfileCommand("Tagged"), tags=tags
        )
    if domain == "character":
        return types.CreateCharacterCommand(
            owner_id=owner, name="Tagged", persona_prompt="Persona", tags=tags
        )
    return types.CreateLorebookCommand(owner_id=owner, title="Tagged", tags=tags)


@pytest.mark.parametrize("domain", ("product", "character", "lorebook"))
async def test_create_assigns_public_tags_and_failure_rolls_back_everything(db, domain):
    owner = uuid4()
    async with use_case_transaction(db):
        await db.execute(
            text("INSERT INTO users(id,email) VALUES (:id,'tag-create@example.test')"),
            {"id": owner},
        )
        await db.execute(
            text("INSERT INTO tags(name,is_active) VALUES ('z inactive',false)")
        )
    service = importlib.import_module(f"app.modules.content.{domain}.service.command")
    with pytest.raises(ValueError, match="Inactive"):
        await getattr(service, "create_" + domain)(
            db, create_command(domain, owner, ("a new", "z inactive"))
        )
    assert await db.scalar(text(f"SELECT count(*) FROM {domain}s")) == 0
    assert await db.scalar(text("SELECT count(*) FROM tags WHERE name='a new'")) == 0
    await db.rollback()
    info = await getattr(service, "create_" + domain)(
        db, create_command(domain, owner, (" Fantasy ", "Fantasy", "fantasy"))
    )
    rows = (
        await db.execute(
            text(
                f"SELECT tag_id,assigned_by,sort_order FROM {domain}_tags WHERE {domain}_id=:id ORDER BY sort_order"
            ),
            {"id": info.id},
        )
    ).all()
    assert len(rows) == 2 and [r.sort_order for r in rows] == [0, 1]
    assert all(r.assigned_by == owner for r in rows)
    assert await db.scalar(text(f"SELECT count(*) FROM {domain}_internal_tags")) == 0


async def test_dictionary_concurrent_same_name_reuses_one_id(db):
    async def resolve():
        async with AsyncSession(db.bind) as session:
            return await TagCommandService.resolve_tags(
                session, TagTypes.ResolveTagsCommand(("same name",))
            )

    first, second = await asyncio.wait_for(
        asyncio.gather(resolve(), resolve()), timeout=15
    )
    assert first[0].id == second[0].id
    assert (
        await db.scalar(text("SELECT count(*) FROM tags WHERE name='same name'")) == 1
    )


@pytest.mark.parametrize("domain", ("product", "character", "lorebook"))
async def test_admin_system_and_inactive_connection_policies(db, domain):
    owner, admin = uuid4(), uuid4()
    async with use_case_transaction(db):
        await db.execute(
            text(
                "INSERT INTO users(id,email,role,status) VALUES (:owner,'tag-owner@example.test','user','active'),(:admin,'tag-admin@example.test','admin','active')"
            ),
            {"owner": owner, "admin": admin},
        )
    command = importlib.import_module(f"app.modules.content.{domain}.service.command")
    service = importlib.import_module(f"app.modules.content.{domain}.service.tags")
    types = importlib.import_module(f"app.modules.content.{domain}.types")
    info = await getattr(command, "create_" + domain)(
        db, create_command(domain, owner, ("shared",))
    )
    result = await service.add_internal_tags(
        db, types.InternalTagsCommand(info.id, admin, ("shared",))
    )
    tag_id = result[0].id
    result = await service.set_system_tags(
        db, types.SystemTagsCommand(info.id, ("shared",))
    )
    assert result[0].source == "admin" and result[0].assigned_by == admin
    with pytest.raises(ValueError, match="administrator"):
        await service.remove_system_tag(
            db, types.SystemTagsCommand(info.id, tag_id=tag_id)
        )
    await TagCommandService.deactivate_tag(
        db, TagTypes.DeactivateTagCommand(tag_id, admin)
    )
    result = await service.replace_public_tags(
        db, types.PublicTagsCommand(info.id, owner, ("shared",))
    )
    assert result[0].is_active is False
    await service.remove_public_tag(
        db, types.PublicTagsCommand(info.id, owner, tag_id=tag_id)
    )
    with pytest.raises(ValueError, match="Inactive"):
        await service.add_public_tags(
            db, types.PublicTagsCommand(info.id, owner, ("shared",))
        )
    with pytest.raises(LookupError):
        await service.add_internal_tags(
            db, types.InternalTagsCommand(info.id, owner, ("forged",))
        )
