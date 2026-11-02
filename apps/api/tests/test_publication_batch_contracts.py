"""Real SQLite publication SQL/FKs via an async adapter; no PostgreSQL locking."""

from collections.abc import Iterator
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import (
    JSON,
    Column,
    Connection,
    ForeignKeyConstraint,
    MetaData,
    Table,
    UniqueConstraint,
    Uuid,
    create_engine,
    event,
    func,
    select,
    text,
    update,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import ORMExecuteState, Session
from sqlalchemy.sql.elements import ClauseElement

from app.db.models.character import Character, CharacterAsset, CharacterImage
from app.db.models.lorebook import Lorebook, LorebookEntry
from app.db.models.product import (
    Product,
    ProductCharacter,
    ProductLorebook,
    ProductLorebookCharacter,
    ProductStartSet,
)
from app.db.models.product_release import ProductReleaseNote
from app.db.models.snapshot.character import (
    CharacterSnapshot,
    CharacterSnapshotAsset,
    CharacterSnapshotImage,
)
from app.db.models.snapshot.lorebook import LorebookSnapshot
from app.db.models.snapshot.product import (
    ProductSnapshot,
    ProductSnapshotCharacter,
    ProductSnapshotLorebook,
    ProductSnapshotLorebookCharacter,
    ProductSnapshotStartSet,
)
from app.modules.content.character import types as CharacterTypes
from app.modules.content.lorebook import types as LorebookTypes
from app.modules.content.product import types as Types
from app.modules.content.product.repository import publication as Repository
from app.modules.content.product.service.command import publication as Builder
from app.modules.content.product.service.command import releases as Releases


@dataclass
class Backend:
    store: Session
    session: AsyncSession
    product_id: UUID
    owner_id: UUID
    character_ids: list[UUID]
    book_ids: list[UUID]
    entry_ids: list[UUID]
    statements: list[str]
    transactions: list[str]
    flushes: list[int]
    requests: list[str]

    def reset_counts(self) -> None:
        self.statements.clear()
        self.transactions.clear()
        self.flushes.clear()
        self.requests.clear()

    async def publish(self) -> Types.ReleaseInfo:
        return await Releases.publish_product(
            self.session,
            Types.PublishCommand(
                product_id=self.product_id,
                owner_id=self.owner_id,
                value=Types.ReleaseNoteCommand("Release", "Release body"),
            ),
        )


@pytest.fixture
def backend(monkeypatch: pytest.MonkeyPatch) -> Iterator[Backend]:
    engine = create_engine("sqlite://")
    metadata = MetaData()
    models = (
        Product,
        Character,
        Lorebook,
        LorebookEntry,
        CharacterImage,
        CharacterAsset,
        ProductCharacter,
        ProductLorebook,
        ProductLorebookCharacter,
        ProductStartSet,
        ProductSnapshot,
        CharacterSnapshot,
        CharacterSnapshotImage,
        CharacterSnapshotAsset,
        LorebookSnapshot,
        ProductSnapshotCharacter,
        ProductSnapshotLorebook,
        ProductSnapshotLorebookCharacter,
        ProductSnapshotStartSet,
        ProductReleaseNote,
    )
    names = {model.__tablename__ for model in models}
    defaults = {
        "id": "(lower(hex(randomblob(16))))",
        "created_at": "CURRENT_TIMESTAMP",
        "updated_at": "CURRENT_TIMESTAMP",
    }
    for model in models:
        model_table = model.__table__
        assert isinstance(model_table, Table)
        table = Table(
            model.__tablename__,
            metadata,
            *(
                Column(
                    column.name,
                    Uuid(native_uuid=False)
                    if isinstance(column.type, Uuid)
                    else JSON()
                    if isinstance(column.type, (JSONB, ARRAY))
                    else column.type,
                    primary_key=column.primary_key,
                    server_default=text(defaults[column.name])
                    if column.name in defaults
                    else None,
                )
                for column in model.__table__.columns
            ),
        )
        for constraint in model_table.constraints:
            if isinstance(constraint, ForeignKeyConstraint) and all(
                element.column.table.name in names for element in constraint.elements
            ):
                table.append_constraint(
                    ForeignKeyConstraint(
                        [element.parent.name for element in constraint.elements],
                        [element.target_fullname for element in constraint.elements],
                    )
                )
            elif isinstance(constraint, UniqueConstraint):
                table.append_constraint(
                    UniqueConstraint(*(column.name for column in constraint.columns))
                )
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
    metadata.create_all(engine)
    statements: list[str] = []
    transactions: list[str] = []
    flushes: list[int] = []
    requests: list[str] = []

    def executed(
        connection: Connection,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", executed)
    try:
        with Session(engine, expire_on_commit=False) as store:

            def requested(state: ORMExecuteState) -> None:
                assert isinstance(state.statement, ClauseElement)
                requests.append(
                    str(state.statement.compile(dialect=postgresql.dialect()))
                )

            event.listen(store, "do_orm_execute", requested)
            owner_id, product_id, model_id = uuid4(), uuid4(), uuid4()
            character_ids = [UUID(int=index) for index in (30, 10, 20)]
            book_ids = [UUID(int=index) for index in (60, 40, 50)]
            entry_ids = [UUID(int=index) for index in range(100, 106)]
            store.add(
                Product(
                    id=product_id,
                    owner_id=owner_id,
                    title="Work",
                    opening_message="Hello",
                    visibility="private",
                    status="draft",
                    default_model_id=model_id,
                    reasoning_effort="low",
                    replacement_policy={},
                )
            )
            store.add_all(
                Character(
                    id=source_id,
                    owner_id=owner_id,
                    name=f"Character {index}",
                    persona_prompt="Persona",
                    visibility="private",
                    status="draft",
                )
                for index, source_id in enumerate(character_ids)
            )
            store.add_all(
                Lorebook(
                    id=source_id,
                    owner_id=owner_id,
                    title=f"Book {index}",
                    visibility="private",
                    status="draft",
                )
                for index, source_id in enumerate(book_ids)
            )
            store.flush()
            character_links = [uuid4() for _ in character_ids]
            book_links = [uuid4() for _ in book_ids]
            store.add_all(
                ProductCharacter(
                    id=link_id,
                    product_id=product_id,
                    character_id=source_id,
                    role_order=index,
                    is_primary=index == 0,
                )
                for index, (link_id, source_id) in enumerate(
                    zip(character_links, character_ids, strict=True)
                )
            )
            store.add_all(
                ProductLorebook(
                    id=link_id,
                    product_id=product_id,
                    lorebook_id=source_id,
                    role="main",
                    priority=index,
                    is_required=True,
                    scope="selected",
                )
                for index, (link_id, source_id) in enumerate(
                    zip(book_links, book_ids, strict=True)
                )
            )
            store.add_all(
                LorebookEntry(
                    id=entry_id,
                    lorebook_id=book_ids[index % len(book_ids)],
                    title=None if index == 0 else f"Start {index}",
                    content=f"Opening {index}",
                    entry_type="start_set",
                    activation_type="always",
                    match_mode="exact",
                    priority=0,
                    placement="before_history",
                    is_enabled=True,
                    metadata_={"studio_scene_v1": {"opening": f"Scene {index}"}},
                )
                for index, entry_id in enumerate(entry_ids)
            )
            store.flush()
            store.add_all(
                ProductLorebookCharacter(
                    product_id=product_id,
                    product_character_id=character_link,
                    product_lorebook_id=book_link,
                )
                for character_link, book_link in zip(
                    character_links, book_links, strict=True
                )
            )
            store.add_all(
                ProductStartSet(
                    product_id=product_id,
                    lorebook_id=book_ids[entry_ids.index(entry_id) % len(book_ids)],
                    entry_id=entry_id,
                    sort_order=index,
                )
                for index, entry_id in enumerate(reversed(entry_ids))
            )
            store.commit()
            store.expunge_all()

            def flushed(session: Session, context: object, instances: object) -> None:
                flushes.append(1)

            event.listen(store, "before_flush", flushed)

            monkeypatch.setattr(
                Builder.SettingsCommandService,
                "_validate_model",
                AsyncMock(
                    return_value=SimpleNamespace(
                        id=model_id,
                        provider_id=uuid4(),
                        model_name="test-model",
                        capabilities={"model_family": "test"},
                    )
                ),
            )
            monkeypatch.setattr(
                Builder.LlmQueryService,
                "get_provider",
                AsyncMock(return_value=SimpleNamespace(name="provider")),
            )

            # pytest's synchronous fixture can own this resource without an event loop.
            # AsyncSession has no connection: only transaction events/SQL methods adapt.
            session = AsyncSession()

            def committed(session: Session) -> None:
                store.commit()
                transactions.append("commit")

            def rolled_back(session: Session) -> None:
                store.rollback()
                transactions.append("rollback")

            event.listen(session.sync_session, "after_commit", committed)
            event.listen(session.sync_session, "after_rollback", rolled_back)
            for name, operation in (
                ("scalar", store.scalar),
                ("scalars", store.scalars),
                ("execute", store.execute),
                ("get", store.get),
                ("flush", store.flush),
            ):
                monkeypatch.setattr(session, name, AsyncMock(side_effect=operation))
            monkeypatch.setattr(session, "add", store.add)
            monkeypatch.setattr(session, "add_all", store.add_all)
            item = Backend(
                store,
                session,
                product_id,
                owner_id,
                character_ids,
                book_ids,
                entry_ids,
                statements,
                transactions,
                flushes,
                requests,
            )
            item.reset_counts()
            try:
                yield item
            finally:
                session.sync_session.close()
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_publication_sql_and_flush_counts(backend: Backend) -> None:
    release = await backend.publish()
    flush = backend.session.flush
    assert isinstance(flush, AsyncMock)
    counts = {
        "selects": sum(sql.startswith("SELECT") for sql in backend.statements),
        "flush_calls": flush.await_count,
        "flush_events": len(backend.flushes),
    }
    assert counts == {"selects": 32, "flush_calls": 14, "flush_events": 11}
    model_validation = Builder.SettingsCommandService._validate_model
    assert isinstance(model_validation, AsyncMock)
    model_validation.assert_awaited_once()
    assert release.version == 1
    assert backend.transactions == ["commit"]
    composition = await Repository.get_snapshot_composition(
        backend.session, release.snapshot_id
    )
    assert len(composition.characters) == 3
    assert len(composition.books) == 3
    assert len(composition.targets) == 3
    assert [start.source_entry_id for start in composition.starts] == list(
        reversed(backend.entry_ids)
    )
    assert all(
        start.title == f"Start {5 - index}"
        for index, start in enumerate(composition.starts[:-1])
    )
    assert composition.starts[-1].title is None
    locks = [sql for sql in backend.requests if "FOR UPDATE" in sql]
    assert "FROM products" in locks[0]
    assert "FROM products" in locks[1]
    assert "FROM characters" in locks[2] and "ORDER BY characters.id" in locks[2]
    assert "FROM lorebooks" in locks[3] and "ORDER BY lorebooks.id" in locks[3]
    # Every downstream single-source freeze still independently checks its owner.
    assert sum("FROM characters" in sql for sql in locks) == 4
    assert sum("FROM lorebooks" in sql for sql in locks) == 4


@pytest.mark.asyncio
async def test_follow_up_versions_digest_and_old_snapshot_survive_edits(
    backend: Backend,
) -> None:
    first = await backend.publish()
    first_snapshot = backend.store.get(ProductSnapshot, first.snapshot_id)
    assert first_snapshot is not None
    first_data = dict(first_snapshot.snapshot_data)
    second = await backend.publish()
    second_snapshot = backend.store.get(ProductSnapshot, second.snapshot_id)
    assert second_snapshot is not None
    assert second.version == 2 and second.snapshot_id != first.snapshot_id
    assert second.change_kind == "media"
    assert second_snapshot.snapshot_data == first_data
    backend.store.execute(
        update(Character)
        .where(Character.id == backend.character_ids[0])
        .values(persona_prompt="Edited")
    )
    backend.store.commit()
    third = await backend.publish()
    assert third.version == 3 and third.change_kind == "content"
    preserved = backend.store.get(ProductSnapshot, first.snapshot_id)
    assert preserved is not None and preserved.snapshot_data == first_data
    for source_id in backend.character_ids:
        assert list(
            backend.store.scalars(
                select(CharacterSnapshot.version)
                .where(CharacterSnapshot.character_id == source_id)
                .order_by(CharacterSnapshot.version)
            )
        ) == [1, 2, 3]
    for source_id in backend.book_ids:
        assert list(
            backend.store.scalars(
                select(LorebookSnapshot.version)
                .where(LorebookSnapshot.lorebook_id == source_id)
                .order_by(LorebookSnapshot.version)
            )
        ) == [1, 2, 3]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["slots", "children", "final", "release"])
async def test_staged_failure_rolls_back_all_snapshots_and_latest(
    backend: Backend, failure: str
) -> None:
    first = await backend.publish()
    backend.reset_counts()
    armed = True

    def fail_after_flush(session: Session, context: object) -> None:
        nonlocal armed
        if not armed:
            return
        inserted = session.new
        if (
            failure == "slots"
            and any(isinstance(item, ProductSnapshotCharacter) for item in inserted)
            or failure == "children"
            and any(isinstance(item, ProductSnapshotStartSet) for item in inserted)
            or failure == "release"
            and any(isinstance(item, ProductReleaseNote) for item in inserted)
            or failure == "final"
            and any(isinstance(item, Product) for item in session.dirty)
        ):
            armed = False
            raise RuntimeError("Injected publication failure")

    event.listen(backend.store, "after_flush", fail_after_flush)
    with pytest.raises(RuntimeError, match="Injected"):
        await backend.publish()
    assert backend.transactions == ["rollback"]
    assert backend.store.scalar(select(func.count()).select_from(ProductSnapshot)) == 1
    assert (
        backend.store.scalar(select(func.count()).select_from(CharacterSnapshot)) == 3
    )
    assert backend.store.scalar(select(func.count()).select_from(LorebookSnapshot)) == 3
    assert (
        backend.store.scalar(select(func.count()).select_from(ProductSnapshotCharacter))
        == 3
    )
    assert (
        backend.store.scalar(select(func.count()).select_from(ProductSnapshotStartSet))
        == 6
    )
    assert (
        backend.store.scalar(select(func.count()).select_from(ProductReleaseNote)) == 1
    )
    product = backend.store.get(Product, backend.product_id)
    assert product is not None and product.latest_snapshot_id == first.snapshot_id
    retry = await backend.publish()
    assert retry.version == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["product", "character", "lorebook"])
async def test_publication_refuses_unowned_sources_before_snapshots(
    backend: Backend, target: str
) -> None:
    if target == "product":
        backend.owner_id = uuid4()
    else:
        model = Character if target == "character" else Lorebook
        source_id = (
            backend.character_ids[0] if target == "character" else backend.book_ids[0]
        )
        backend.store.execute(
            update(model).where(model.id == source_id).values(owner_id=uuid4())
        )
        backend.store.commit()
    backend.reset_counts()
    with pytest.raises(LookupError):
        await backend.publish()
    assert backend.transactions == ["rollback"]
    assert backend.store.scalar(select(func.count()).select_from(ProductSnapshot)) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["product", "character", "lorebook"])
async def test_public_commands_refuse_missing_sources(
    backend: Backend, target: str
) -> None:
    with pytest.raises(LookupError):
        if target == "product":
            backend.product_id = uuid4()
            await backend.publish()
        elif target == "character":
            await Builder.CharacterCommandService.freeze_character(
                backend.session,
                CharacterTypes.FreezeCharacterCommand(
                    character_id=uuid4(), owner_id=backend.owner_id
                ),
            )
        else:
            await Builder.LorebookCommandService.freeze_lorebook(
                backend.session,
                LorebookTypes.FreezeLorebookCommand(
                    lorebook_id=uuid4(), owner_id=backend.owner_id
                ),
            )
    assert backend.transactions == ["rollback"]
    assert backend.store.scalar(select(func.count()).select_from(ProductSnapshot)) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", ["disabled", "type", "empty"])
async def test_changed_start_selection_is_rejected_before_writes(
    backend: Backend, invalid: str
) -> None:
    if invalid == "empty":
        backend.store.query(ProductStartSet).delete()
    else:
        fields = (
            {"is_enabled": False} if invalid == "disabled" else {"entry_type": "world"}
        )
        backend.store.execute(
            update(LorebookEntry)
            .where(LorebookEntry.id == backend.entry_ids[0])
            .values(**fields)
        )
    backend.store.commit()
    backend.reset_counts()
    with pytest.raises(ValueError, match="start option|Start options"):
        await backend.publish()
    assert backend.transactions == ["rollback"]
    assert not backend.flushes


@pytest.mark.asyncio
async def test_start_parent_fk_rejects_mismatched_entry(backend: Backend) -> None:
    with pytest.raises(IntegrityError):
        backend.store.execute(
            update(ProductStartSet)
            .where(ProductStartSet.entry_id == backend.entry_ids[0])
            .values(lorebook_id=backend.book_ids[1])
        )
    backend.store.rollback()
    release = await backend.publish()
    assert release.version == 1


@pytest.mark.asyncio
async def test_builder_requires_caller_transaction(backend: Backend) -> None:
    with pytest.raises(RuntimeError, match="caller transaction"):
        await Builder._build_publication(
            backend.session,
            Types.BuildPublicationCommand(
                product_id=backend.product_id, owner_id=backend.owner_id
            ),
        )
    assert not backend.statements
