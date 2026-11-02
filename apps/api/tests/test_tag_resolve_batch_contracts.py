"""Tag resolve SQL and rollback through SQLite; PG compilation is not PG locking."""

import asyncio
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Connection,
    DateTime,
    MetaData,
    Result,
    ScalarResult,
    Table,
    Text,
    Uuid,
    create_engine,
    event,
    func,
    select,
    text,
    update,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import ORMExecuteState, Session
from sqlalchemy.sql.base import Executable
from sqlalchemy.sql.elements import ClauseElement

from app.db.models.tag import Tag
from app.db.transaction import use_case_transaction
from app.modules.content.tag import repository as Repository
from app.modules.content.tag import types as Types
from app.modules.content.tag.service import command as Service


@dataclass
class Backend:
    store: Session
    session: AsyncSession
    statements: list[str]
    requests: list[tuple[str, dict[str, object]]]
    transactions: list[str]

    def seed(self, name: str, *, active: bool = True) -> Tag:
        entity = Tag(id=uuid4(), name=name, description="original", is_active=active)
        self.store.add(entity)
        self.store.commit()
        self.statements.clear()
        self.requests.clear()
        return entity


@pytest.fixture
def backend(monkeypatch: pytest.MonkeyPatch) -> Iterator[Backend]:
    engine = create_engine("sqlite://")
    with engine.connect() as connection:
        driver = connection.connection.driver_connection
        assert isinstance(driver, sqlite3.Connection)
        driver.create_function("gen_random_uuid", 0, lambda: uuid4().hex)
    metadata = MetaData()
    Table(
        "tags",
        metadata,
        Column(
            "id",
            Uuid(native_uuid=False),
            primary_key=True,
            server_default=text("(gen_random_uuid())"),
        ),
        Column("name", Text, nullable=False, unique=True),
        Column("description", Text),
        Column("is_active", Boolean, nullable=False, server_default=text("true")),
        Column("created_at", DateTime, nullable=False, server_default=func.now()),
        Column("updated_at", DateTime, nullable=False, server_default=func.now()),
        CheckConstraint("trim(name) <> ''"),
    )
    metadata.create_all(engine)
    statements: list[str] = []
    requests: list[tuple[str, dict[str, object]]] = []
    transactions: list[str] = []

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
            session = AsyncSession()

            def committed(session: Session) -> None:
                store.commit()
                transactions.append("commit")

            def rolled_back(session: Session) -> None:
                store.rollback()
                transactions.append("rollback")

            def requested(state: ORMExecuteState) -> None:
                statement = state.statement
                assert isinstance(statement, ClauseElement)
                compiled = statement.compile(
                    dialect=postgresql.dialect(),
                    compile_kwargs={"render_postcompile": True},
                )
                requests.append((str(compiled), dict(compiled.params or {})))

            event.listen(session.sync_session, "after_commit", committed)
            event.listen(session.sync_session, "after_rollback", rolled_back)
            event.listen(store, "do_orm_execute", requested)
            for name, operation in (
                ("execute", store.execute),
                ("scalars", store.scalars),
            ):
                monkeypatch.setattr(session, name, AsyncMock(side_effect=operation))
            yield Backend(store, session, statements, requests, transactions)
            session.sync_session.close()
    finally:
        engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [0, 1, 3, 499, 500, 501, 1001])
async def test_resolve_sql_measurement(backend: Backend, count: int) -> None:
    names = tuple(f"tag-{index:04}" for index in reversed(range(count)))
    result = await Service.resolve_tags(
        backend.session, Types.ResolveTagsCommand(names)
    )
    inserts = sum(statement.startswith("INSERT") for statement in backend.statements)
    selects = sum(statement.startswith("SELECT") for statement in backend.statements)
    print(f"U25_TAG_SQL names={count}: INSERT={inserts} SELECT={selects}")
    assert inserts == selects == (count + 499) // 500
    assert tuple(info.name for info in result) == names
    assert len({info.id for info in result}) == count
    assert all(isinstance(info, Types.TagInfo) for info in result)
    assert backend.transactions == ["commit"]
    inserted_names: list[str] = []
    locked_names: list[str] = []
    for sql, params in backend.requests:
        if sql.startswith("INSERT"):
            assert "ON CONFLICT (name) DO NOTHING" in sql
            batch = [
                value for name, value in params.items() if name.startswith("name_m")
            ]
            assert 0 < len(batch) <= 500
            assert all(isinstance(value, str) for value in batch)
            inserted_names.extend(value for value in batch if isinstance(value, str))
            assert "description" not in params and "is_active" not in params
        else:
            assert "ORDER BY CASE tags.name" in sql and "FOR SHARE" in sql
            assert "FOR UPDATE" not in sql
            assert len(params) <= 1500
            locked_names.extend(
                value
                for name, value in params.items()
                if name.startswith("param_") and isinstance(value, str)
            )
    assert inserted_names == locked_names == sorted(names)


@pytest.mark.asyncio
async def test_trim_dedup_exact_unicode_and_input_order_are_preserved(
    backend: Backend,
) -> None:
    names = (" Z ", "A", "Z", "a", "현대  판타지", "é", "e\u0301")
    command = Types.ResolveTagsCommand(names)
    first = await Service.resolve_tags(backend.session, command)
    second = await Service.resolve_tags(backend.session, command)
    assert [info.name for info in first] == [
        "Z",
        "A",
        "a",
        "현대  판타지",
        "é",
        "e\u0301",
    ]
    assert first == second and command.names == names
    assert backend.store.scalar(select(func.count()).select_from(Tag)) == 6


@pytest.mark.asyncio
@pytest.mark.parametrize("retained", [False, True])
async def test_existing_inactive_ids_are_only_allowed_when_retained(
    backend: Backend, retained: bool
) -> None:
    entity = backend.seed("B", active=False)
    command = Types.ResolveTagsCommand(
        ("New", "B"), (entity.id,) if retained else (uuid4(),)
    )
    if retained:
        result = await Service.resolve_tags(backend.session, command)
        assert [info.name for info in result] == ["New", "B"]
        assert result[1] == Types.TagInfo(entity.id, "B", "original", False)
    else:
        with pytest.raises(
            ValueError, match="^Inactive tags cannot be newly assigned\\.$"
        ):
            await Service.resolve_tags(backend.session, command)
        assert list(backend.store.scalars(select(Tag.name))) == ["B"]
        assert backend.transactions == ["rollback"]


@pytest.mark.asyncio
async def test_shared_query_refreshes_identity_map_before_inactive_validation(
    backend: Backend,
) -> None:
    entity = backend.seed("B")
    backend.store.execute(
        update(Tag)
        .where(Tag.id == entity.id)
        .values(is_active=False)
        .execution_options(synchronize_session=False)
    )
    backend.store.commit()
    assert entity.is_active
    with pytest.raises(ValueError, match="Inactive"):
        await Service.resolve_tags(backend.session, Types.ResolveTagsCommand(("B",)))


@pytest.mark.asyncio
@pytest.mark.parametrize("names", [("",), (" \t",), ("Valid", " ")])
async def test_invalid_names_fail_before_sql(
    backend: Backend, names: tuple[str, ...]
) -> None:
    with pytest.raises(ValueError, match="nonblank strings"):
        await Service.resolve_tags(backend.session, Types.ResolveTagsCommand(names))
    assert backend.statements == [] and backend.transactions == []


@pytest.mark.asyncio
async def test_missing_renamed_result_keeps_retry_error_and_rolls_back_new_names(
    backend: Backend, monkeypatch: pytest.MonkeyPatch
) -> None:
    entity = backend.seed("B")

    async def renamed_before_select(statement: Executable) -> ScalarResult[Tag]:
        backend.store.execute(
            update(Tag).where(Tag.id == entity.id).values(name="Renamed")
        )
        return backend.store.scalars(statement)

    monkeypatch.setattr(backend.session, "scalars", renamed_before_select)
    with pytest.raises(
        ValueError, match="^Tag name changed concurrently; retry the request\\.$"
    ):
        await Service.resolve_tags(
            backend.session, Types.ResolveTagsCommand(("A", "B"))
        )
    assert list(backend.store.scalars(select(Tag.name))) == ["B"]
    assert backend.transactions == ["rollback"]


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["insert", "select"])
@pytest.mark.parametrize("caught", [False, True])
async def test_second_batch_failure_rolls_back_dictionary_and_outer_writes(
    backend: Backend, monkeypatch: pytest.MonkeyPatch, phase: str, caught: bool
) -> None:
    entity = backend.seed("existing")
    calls = 0

    async def execute_then_fail(statement: Executable) -> Result[tuple[object, ...]]:
        nonlocal calls
        result = backend.store.execute(statement)
        calls += 1
        if calls == 2:
            raise RuntimeError("batch failed")
        return result

    async def select_then_fail(statement: Executable) -> ScalarResult[Tag]:
        nonlocal calls
        result = backend.store.scalars(statement)
        calls += 1
        if calls == 2:
            raise RuntimeError("batch failed")
        return result

    monkeypatch.setattr(
        backend.session,
        "execute" if phase == "insert" else "scalars",
        execute_then_fail if phase == "insert" else select_then_fail,
    )
    command = Types.ResolveTagsCommand(
        tuple(f"tag-{index:04}" for index in range(1001))
    )
    with pytest.raises(
        RuntimeError, match="nested use case failed" if caught else "batch failed"
    ):
        async with use_case_transaction(backend.session):
            backend.store.execute(
                update(Tag).where(Tag.id == entity.id).values(description="changed")
            )
            if caught:
                with pytest.raises(RuntimeError, match="batch failed"):
                    await Service.resolve_tags(backend.session, command)
            else:
                await Service.resolve_tags(backend.session, command)
    assert list(backend.store.scalars(select(Tag.name))) == ["existing"]
    assert backend.store.scalar(select(Tag.description)) == "original"
    assert backend.transactions == ["rollback"] and not backend.session.in_transaction()


@pytest.mark.asyncio
async def test_successful_resolve_does_not_commit_outer_scope(backend: Backend) -> None:
    with pytest.raises(ValueError, match="later failure"):
        async with use_case_transaction(backend.session):
            await Service.resolve_tags(
                backend.session, Types.ResolveTagsCommand(("A", "B"))
            )
            assert backend.transactions == []
            raise ValueError("later failure")
    assert backend.store.scalar(select(func.count()).select_from(Tag)) == 0
    assert backend.transactions == ["rollback"]


@pytest.mark.asyncio
async def test_repository_deduplicates_before_bounded_insertion(
    backend: Backend,
) -> None:
    async with use_case_transaction(backend.session):
        entities = await Repository.resolve_tags(backend.session, ("B", "A", "B"))
    assert [entity.name for entity in entities] == ["A", "B"]
    assert len(backend.requests) == 2


@pytest.mark.asyncio
async def test_single_admin_create_keeps_existing_description_and_id(
    backend: Backend, monkeypatch: pytest.MonkeyPatch
) -> None:
    entity = backend.seed("A")
    monkeypatch.setattr(Service.IdentityQueryService, "require_admin", AsyncMock())
    result = await Service.create_tag(
        backend.session, Types.CreateTagCommand(uuid4(), " A ", "changed")
    )
    assert result == Types.TagInfo(entity.id, "A", "original", True)


@pytest.mark.asyncio
async def test_mixed_existing_and_new_names_preserve_existing_fields(
    backend: Backend,
) -> None:
    existing = backend.seed("existing")
    before = (
        existing.id,
        existing.description,
        existing.is_active,
        existing.created_at,
        existing.updated_at,
    )
    result = await Service.resolve_tags(
        backend.session, Types.ResolveTagsCommand(("new", "existing"))
    )
    assert [info.name for info in result] == ["new", "existing"]
    assert (
        existing.id,
        existing.description,
        existing.is_active,
        existing.created_at,
        existing.updated_at,
    ) == before
    assert result[1].id == existing.id


@pytest.mark.asyncio
async def test_cancelled_batch_rolls_back_completed_inserts(
    backend: Backend, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def cancelled_after_write(
        statement: Executable,
    ) -> Result[tuple[object, ...]]:
        backend.store.execute(statement)
        raise asyncio.CancelledError("caller stopped")

    monkeypatch.setattr(backend.session, "execute", cancelled_after_write)
    with pytest.raises(asyncio.CancelledError, match="caller stopped"):
        await Service.resolve_tags(backend.session, Types.ResolveTagsCommand(("new",)))
    assert backend.store.scalar(select(func.count()).select_from(Tag)) == 0
    assert backend.transactions == ["rollback"]


@pytest.mark.asyncio
async def test_unrelated_existing_transaction_is_not_adopted(backend: Backend) -> None:
    await backend.session.begin()
    try:
        with pytest.raises(InvalidRequestError, match="transaction is already begun"):
            await Service.resolve_tags(
                backend.session, Types.ResolveTagsCommand(("new",))
            )
        assert backend.statements == []
    finally:
        await backend.session.rollback()
