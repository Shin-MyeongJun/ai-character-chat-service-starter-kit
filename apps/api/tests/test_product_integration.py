from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.db.models.character import Character
from app.db.models.identity import User
from app.db.models.lorebook import Lorebook, LorebookEntry
from app.db.models.product import (
    Product,
    ProductCharacter,
    ProductLorebook,
    ProductLorebookCharacter,
)
from app.db.transaction import use_case_transaction
from app.modules.chatting.conversation import types as ConversationTypes
from app.modules.content.lorebook import types as LorebookTypes
from app.modules.content.product import types as ProductTypes
from app.modules.content.product.service import command
from app.modules.content.product.service.command import composition
from app.modules.content.product.types import (
    CharacterSelection,
    LorebookSelection,
    ProductCompositionInfo,
    ProductProfileCommand,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.asyncio


async def seed(db):
    async with use_case_transaction(db):
        owner = User(id=uuid4(), email=f"{uuid4()}@test.local")
        db.add(owner)
        await db.flush()
        c = Character(id=uuid4(), owner_id=owner.id, name="C", persona_prompt="P")
        b = Lorebook(id=uuid4(), owner_id=owner.id, title="B")
        db.add_all([c, b])
    return (SimpleNamespace(id=owner.id), c, b)


async def test_composition_ownership_and_cross_product_fk(db):
    owner, c, b = await seed(db)
    p = await command.create_product(
        db,
        ProductTypes.CreateProductCommand(
            owner_id=owner.id, value=ProductProfileCommand("P")
        ),
    )
    value = ProductCompositionInfo(
        (CharacterSelection(c.id, True),),
        (LorebookSelection(b.id, "selected", (c.id,)),),
    )
    assert (
        await composition.replace_composition(
            db,
            ProductTypes.ReplaceCompositionCommand(
                product_id=p.id, owner_id=owner.id, value=value
            ),
        )
        == value
    )
    with pytest.raises(LookupError):
        await composition.replace_composition(
            db,
            ProductTypes.ReplaceCompositionCommand(
                product_id=p.id, owner_id=uuid4(), value=value
            ),
        )
    async with use_case_transaction(db):
        foreign = Product(id=uuid4(), owner_id=owner.id, title="foreign")
        db.add(foreign)
        await db.flush()
        other = ProductCharacter(
            id=uuid4(),
            product_id=foreign.id,
            character_id=value.characters[0].character_id,
        )
        db.add(other)
        await db.flush()
        target = await db.scalar(
            select(ProductLorebook).where(ProductLorebook.product_id == p.id)
        )
        with pytest.raises(IntegrityError):
            async with db.begin_nested():
                db.add(
                    ProductLorebookCharacter(
                        product_id=p.id,
                        product_character_id=other.id,
                        product_lorebook_id=target.id,
                    )
                )
                await db.flush()


async def test_foreign_content_cannot_be_added(db):
    _owner, c, _b = await seed(db)
    other, _, _ = await seed(db)
    p = await command.create_product(
        db,
        ProductTypes.CreateProductCommand(
            owner_id=other.id, value=ProductProfileCommand("P")
        ),
    )
    with pytest.raises(LookupError):
        await composition.replace_composition(
            db,
            ProductTypes.ReplaceCompositionCommand(
                product_id=p.id,
                owner_id=other.id,
                value=ProductCompositionInfo((CharacterSelection(c.id),), ()),
            ),
        )


async def test_start_sets_do_not_activate_as_regular_lore(db):
    from app.modules.content.lorebook import repository as lore_repo
    from app.modules.content.lorebook.service import query

    _owner, _c, b = await seed(db)
    async with use_case_transaction(db):
        db.add_all(
            [
                LorebookEntry(
                    lorebook_id=b.id,
                    content="Begin at home",
                    entry_type="start_set",
                    activation_type="always",
                ),
                LorebookEntry(
                    lorebook_id=b.id,
                    content="World",
                    entry_type="world",
                    activation_type="always",
                ),
            ]
        )
    entries = await query.get_always_entries(
        db, LorebookTypes.GetAlwaysEntriesCommand(lorebook_ids=[b.id])
    )
    assert len(entries) == 1
    assert entries[0].content == "World"
    assert len(await lore_repo.list_start_sets(db, b.id)) == 1


async def ready_product(db):
    from app.db.models.model_routing import Model, Provider
    from app.modules.content.product.service.command.settings import set_settings
    from app.modules.content.product.types import ProductSettingsInfo

    owner, c, b = await seed(db)
    async with use_case_transaction(db):
        provider = Provider(id=uuid4(), name=str(uuid4()))
        db.add(provider)
        await db.flush()
        model = Model(
            id=uuid4(),
            provider_id=provider.id,
            model_name="model-v1",
            display_name="test",
            context_window=32000,
            input_price=1,
            output_price=1,
            capabilities={"reasoning_efforts": ["low", "high"], "model_family": "test"},
        )
        entry = LorebookEntry(
            id=uuid4(),
            lorebook_id=b.id,
            title="Home",
            content="Begin at home",
            entry_type="start_set",
        )
        db.add_all([model, entry])
    p = await command.create_product(
        db,
        ProductTypes.CreateProductCommand(
            owner_id=owner.id, value=ProductProfileCommand("P", opening_message="Hello")
        ),
    )
    value = ProductCompositionInfo(
        (CharacterSelection(c.id, True),), (LorebookSelection(b.id),)
    )
    await composition.replace_composition(
        db,
        ProductTypes.ReplaceCompositionCommand(
            product_id=p.id, owner_id=owner.id, value=value
        ),
    )
    await set_settings(
        db,
        ProductTypes.SetSettingsCommand(
            product_id=p.id,
            owner_id=owner.id,
            value=ProductSettingsInfo(model.id, "low", (entry.id,)),
        ),
    )
    return (owner, c, b, p, SimpleNamespace(id=model.id), entry)


async def test_settings_and_composition_preserve_start_selection(db):
    from app.db.models.product import ProductStartSet
    from app.modules.content.product.service.command.settings import (
        _validate_publication,
        set_settings,
    )
    from app.modules.content.product.types import ProductSettingsInfo

    owner, c, b, p, model, entry = await ready_product(db)
    await composition.replace_composition(
        db,
        ProductTypes.ReplaceCompositionCommand(
            product_id=p.id,
            owner_id=owner.id,
            value=ProductCompositionInfo(
                (CharacterSelection(c.id, True),), (LorebookSelection(b.id),)
            ),
        ),
    )
    async with use_case_transaction(db):
        row = await db.get(Product, p.id)
        await _validate_publication(db, row)
        assert (
            len(
                list(
                    await db.scalars(
                        select(ProductStartSet).where(
                            ProductStartSet.product_id == p.id
                        )
                    )
                )
            )
            == 1
        )
    with pytest.raises(ValueError, match="reasoning"):
        await set_settings(
            db,
            ProductTypes.SetSettingsCommand(
                product_id=p.id,
                owner_id=owner.id,
                value=ProductSettingsInfo(model.id, "max", (entry.id,)),
            ),
        )
    with pytest.raises(ValueError, match="start_set"):
        await set_settings(
            db,
            ProductTypes.SetSettingsCommand(
                product_id=p.id,
                owner_id=owner.id,
                value=ProductSettingsInfo(model.id, "low", (uuid4(),)),
            ),
        )


async def test_snapshot_media_survives_source_deletion(db):
    from app.db.models.character import CharacterAsset, CharacterImage
    from app.db.models.snapshot.character import (
        CharacterSnapshot,
        CharacterSnapshotImage,
    )
    from app.modules.content.character.service.command import freeze_character
    from app.modules.content.character.types import FreezeCharacterCommand
    from app.modules.content.product.service.views.snapshots import (
        check_media_reference,
    )

    _owner, c, _b = await seed(db)
    async with use_case_transaction(db):
        db.add_all(
            [
                CharacterImage(
                    character_id=c.id,
                    emotion_tag="normal",
                    image_url="immutable/image/v1",
                    is_default=True,
                ),
                CharacterAsset(
                    character_id=c.id,
                    asset_type="audio",
                    purpose="voice",
                    file_url="immutable/audio/v1",
                ),
            ]
        )
        await db.flush()
        snapshot = await freeze_character(db, FreezeCharacterCommand(c.id, _owner.id))
        sid = snapshot.id
    async with use_case_transaction(db):
        await db.delete(c)
    async with use_case_transaction(db):
        db.expire_all()
        saved = await db.get(CharacterSnapshot, sid)
        assert saved.character_id is None
        assert saved.snapshot_data["persona_prompt"] == "P"
        assert (
            await check_media_reference(
                db, ProductTypes.MediaIsReferencedCommand(url="immutable/image/v1")
            )
        ).referenced
        assert (
            await db.scalar(
                select(CharacterSnapshotImage).where(
                    CharacterSnapshotImage.character_snapshot_id == sid
                )
            )
        ).is_default


async def test_atomic_publication_and_original_edits(db):
    from app.db.models.snapshot.character import CharacterSnapshot
    from app.db.models.snapshot.product import (
        ProductSnapshot,
        ProductSnapshotCharacter,
        ProductSnapshotStartSet,
    )
    from app.modules.content.product.service.command.publication import (
        _build_publication,
    )

    owner, c, _b, p, _model, _entry = await ready_product(db)
    async with use_case_transaction(db):
        first = await _build_publication(
            db, ProductTypes.BuildPublicationCommand(product_id=p.id, owner_id=owner.id)
        )
        first_id = first.id
    async with use_case_transaction(db):
        c.persona_prompt = "New persona"
    with pytest.raises(RuntimeError):
        async with use_case_transaction(db):
            await _build_publication(
                db,
                ProductTypes.BuildPublicationCommand(
                    product_id=p.id, owner_id=owner.id
                ),
            )
            raise RuntimeError("simulate publication failure")
    async with use_case_transaction(db):
        db.expire_all()
        product = await db.get(Product, p.id)
        assert product.latest_snapshot_id == first_id
        assert (
            len(
                list(
                    await db.scalars(
                        select(ProductSnapshot).where(
                            ProductSnapshot.product_id == p.id
                        )
                    )
                )
            )
            == 1
        )
        link = await db.scalar(
            select(ProductSnapshotCharacter).where(
                ProductSnapshotCharacter.product_snapshot_id == first_id
            )
        )
        assert (
            await db.get(CharacterSnapshot, link.character_snapshot_id)
        ).snapshot_data["persona_prompt"] == "P"
        second = await _build_publication(
            db,
            ProductTypes.BuildPublicationCommand(
                product_id=p.id, owner_id=product.owner_id
            ),
        )
        assert second.version == 2
        assert (
            second.snapshot_data["content_digest"]
            != (await db.get(ProductSnapshot, first_id)).snapshot_data["content_digest"]
        )
        assert (
            len(
                list(
                    await db.scalars(
                        select(ProductSnapshotStartSet).where(
                            ProductSnapshotStartSet.product_snapshot_id == second.id
                        )
                    )
                )
            )
            == 1
        )


async def test_release_policy_and_typo_correction(db):
    from app.db.models.product_release import ProductReleaseNoteRevision
    from app.modules.content.product.service.command.releases import (
        correct_note,
        publish_product,
    )
    from app.modules.content.product.types import ReleaseNoteCommand

    owner, c, _b, p, _model, _entry = await ready_product(db)
    first = await publish_product(
        db,
        ProductTypes.PublishCommand(
            product_id=p.id,
            owner_id=owner.id,
            value=ReleaseNoteCommand("First", "Initial release", True),
        ),
    )
    assert first.update_policy == "choice"
    media = await publish_product(
        db,
        ProductTypes.PublishCommand(
            product_id=p.id,
            owner_id=owner.id,
            value=ReleaseNoteCommand("Media", "No content change", True),
        ),
    )
    assert media.update_policy == "automatic"
    async with use_case_transaction(db):
        c.persona_prompt = "Changed"
    changed = await publish_product(
        db,
        ProductTypes.PublishCommand(
            product_id=p.id,
            owner_id=owner.id,
            value=ReleaseNoteCommand("Changes", "Content changed", True),
        ),
    )
    assert changed.change_kind == "content" and changed.update_policy == "choice"
    corrected = await correct_note(
        db,
        ProductTypes.CorrectNoteCommand(
            product_id=p.id,
            snapshot_id=changed.snapshot_id,
            owner_id=owner.id,
            summary="Corrected",
            body="Typo corrected",
        ),
    )
    assert corrected.update_policy == "choice"
    async with use_case_transaction(db):
        assert len(list(await db.scalars(select(ProductReleaseNoteRevision)))) == 1


async def test_conversation_keeps_published_context(db):
    from app.modules.chatting.conversation.service import (
        prepare_runtime_context,
        start_conversation,
    )
    from app.modules.content.product.service.command.releases import publish_product
    from app.modules.content.product.types import ReleaseNoteCommand

    owner, c, _b, p, _model, entry = await ready_product(db)
    first = await publish_product(
        db,
        ProductTypes.PublishCommand(
            product_id=p.id,
            owner_id=owner.id,
            value=ReleaseNoteCommand("First", "First"),
        ),
    )
    conversation = await start_conversation(
        db,
        ConversationTypes.StartConversationCommand(product_id=p.id, user_id=owner.id),
    )
    async with use_case_transaction(db):
        c.persona_prompt = "new content"
        entry.content = "new starting point"
    await publish_product(
        db,
        ProductTypes.PublishCommand(
            product_id=p.id,
            owner_id=owner.id,
            value=ReleaseNoteCommand("Update", "Update"),
        ),
    )
    async with use_case_transaction(db):
        context = await prepare_runtime_context(
            db,
            ConversationTypes.PrepareRuntimeContextCommand(
                conversation_id=conversation.id, user_id=owner.id
            ),
        )
        assert context.product_snapshot_id == str(first.snapshot_id)
        assert context.characters[0].data["persona_prompt"] == "P"
        assert context.start.content == "Begin at home"
        assert context.lorebooks[0].entries == []
    with pytest.raises(LookupError):
        await prepare_runtime_context(
            db,
            ConversationTypes.PrepareRuntimeContextCommand(
                conversation_id=conversation.id, user_id=uuid4()
            ),
        )


async def test_version_switch_requires_consent_and_preserves_initial_context(db):
    from app.db.models.chat import Conversation, ConversationVersionChange, Message
    from app.modules.chatting.conversation.service import start_conversation
    from app.modules.chatting.conversation.service.command.versions import (
        switch_version,
    )
    from app.modules.content.product.service.command.releases import publish_product
    from app.modules.content.product.types import ReleaseNoteCommand

    owner, c, _b, p, _model, _entry = await ready_product(db)
    first = await publish_product(
        db,
        ProductTypes.PublishCommand(
            product_id=p.id,
            owner_id=owner.id,
            value=ReleaseNoteCommand("First", "First"),
        ),
    )
    conversation = await start_conversation(
        db,
        ConversationTypes.StartConversationCommand(product_id=p.id, user_id=owner.id),
    )
    async with use_case_transaction(db):
        c.persona_prompt = "Changed"
    await publish_product(
        db,
        ProductTypes.PublishCommand(
            product_id=p.id,
            owner_id=owner.id,
            value=ReleaseNoteCommand("Content", "Content"),
        ),
    )
    latest = await publish_product(
        db,
        ProductTypes.PublishCommand(
            product_id=p.id,
            owner_id=owner.id,
            value=ReleaseNoteCommand("Media", "Media", True),
        ),
    )
    with pytest.raises(ValueError, match="consent"):
        await switch_version(
            db,
            ConversationTypes.SwitchVersionCommand(
                conversation_id=conversation.id,
                user_id=owner.id,
                target_snapshot_id=latest.snapshot_id,
                automatic=True,
            ),
        )
    async with use_case_transaction(db):
        product = await db.get(Product, p.id)
        uid = product.owner_id
    await switch_version(
        db,
        ConversationTypes.SwitchVersionCommand(
            conversation_id=conversation.id,
            user_id=uid,
            target_snapshot_id=latest.snapshot_id,
        ),
    )
    async with use_case_transaction(db):
        saved = await db.get(Conversation, conversation.id)
        assert saved.initial_snapshot_id == first.snapshot_id
        assert saved.start_set_id == conversation.start_set_id
        assert (
            len(
                list(
                    await db.scalars(
                        select(Message).where(Message.conversation_id == saved.id)
                    )
                )
            )
            == 1
        )
        assert len(list(await db.scalars(select(ConversationVersionChange)))) == 1
