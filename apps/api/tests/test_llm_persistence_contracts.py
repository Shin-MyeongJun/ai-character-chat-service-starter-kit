"""Offline LLM storage/query contracts; no provider APIs or PostgreSQL locks."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import assert_type
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import JSON, Column, MetaData, Table, Uuid, create_engine, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.db.models.model_routing import Model, ModelReplacement, Provider
from app.modules.llm import repository as Repository
from app.modules.llm import types as Types
from app.modules.llm.mapper import persistence as PersistenceMapper
from app.modules.llm.service import query as QueryService

NOW = datetime(2026, 10, 28, tzinfo=UTC)


def _model(provider_id: UUID, *, model_id: UUID | None = None) -> Model:
    return Model(
        id=model_id or uuid4(),
        provider_id=provider_id,
        model_name="stored-model",
        display_name="Stored model",
        context_window=32000,
        input_price=Decimal("0.123456"),
        output_price=Decimal("0.654321"),
        is_enabled=True,
        capabilities={"reasoning_efforts": ["low"], "nested": {"values": [1]}},
        retirement_announced_at=None,
        shutdown_at=None,
        created_at=NOW,
        updated_at=NOW,
    )


@pytest.fixture
def model_database() -> Iterator[tuple[Session, AsyncMock]]:
    engine = create_engine("sqlite://")
    metadata = MetaData()
    # Read predicates use real SQL. PostgreSQL FKs/uniqueness/locking are separate.
    for entity_type in (Provider, Model, ModelReplacement):
        Table(
            entity_type.__tablename__,
            metadata,
            *(
                Column(
                    column.name,
                    Uuid(native_uuid=False)
                    if isinstance(column.type, Uuid)
                    else JSON()
                    if isinstance(column.type, JSONB)
                    else column.type,
                    primary_key=column.primary_key,
                )
                for column in entity_type.__table__.columns
            ),
        )
    metadata.create_all(engine)
    try:
        with Session(engine) as sync_session:
            session = AsyncMock(spec=AsyncSession)
            session.get.side_effect = sync_session.get
            session.scalars.side_effect = sync_session.scalars
            session.execute.side_effect = sync_session.execute
            yield sync_session, session
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_direct_lookups_preserve_disabled_and_missing_results(
    model_database: tuple[Session, AsyncMock],
) -> None:
    sync_session, session = model_database
    provider = Provider(id=uuid4(), name="disabled", is_enabled=False)
    model = _model(provider.id)
    model.is_enabled = False
    model.shutdown_at = NOW - timedelta(days=1)
    sync_session.add_all([provider, model])
    sync_session.flush()

    model_info = await QueryService.get_model(
        session=session, command=Types.GetModelCommand(model.id)
    )
    assert model_info is not None and model_info.id == model.id
    assert not model_info.is_enabled and model_info.shutdown_at == model.shutdown_at
    session.get.assert_awaited_with(Model, model.id)
    assert await QueryService.get_provider(
        session, Types.GetProviderCommand(provider.id)
    ) == Types.ProviderInfo(provider.id, "disabled", False)
    session.get.assert_awaited_with(Provider, provider.id)
    assert await QueryService.get_model(session, Types.GetModelCommand(uuid4())) is None
    assert (
        await QueryService.get_provider(session, Types.GetProviderCommand(uuid4()))
        is None
    )
    session.commit.assert_not_awaited()
    session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_candidates_filter_only_enabled_providers(
    model_database: tuple[Session, AsyncMock],
) -> None:
    sync_session, session = model_database
    assert await QueryService.list_candidate_models(session) == []
    enabled = Provider(id=uuid4(), name="enabled", is_enabled=True)
    disabled = Provider(id=uuid4(), name="disabled", is_enabled=False)
    active, inactive, retired = [_model(enabled.id) for _ in range(3)]
    inactive.is_enabled = False
    retired.shutdown_at = NOW - timedelta(days=1)
    retired.capabilities = {}
    hidden = _model(disabled.id)
    orphan = _model(uuid4())
    sync_session.add_all([enabled, disabled, active, inactive, retired, hidden, orphan])
    sync_session.flush()

    infos = await QueryService.list_candidate_models(session)
    assert {info.id for info in infos} == {active.id, inactive.id, retired.id}
    assert all(isinstance(info, Types.ModelInfo) for info in infos)
    # Candidate ordering is deliberately unspecified; keep the SQL unsorted.
    statement = session.scalars.await_args.args[0]
    assert "ORDER BY" not in str(statement).upper()


@pytest.mark.asyncio
async def test_candidate_mapping_preserves_storage_iteration_order() -> None:
    session = AsyncMock(spec=AsyncSession)
    entities = [_model(uuid4(), model_id=UUID(int=i)) for i in (9, 1, 5)]
    session.scalars.return_value = iter(entities)
    infos = await QueryService.list_candidate_models(session)
    assert [info.id for info in infos] == [entity.id for entity in entities]


@pytest.mark.asyncio
async def test_refresh_lookups_replace_cached_model_and_provider_values(
    model_database: tuple[Session, AsyncMock],
) -> None:
    sync_session, session = model_database
    provider = Provider(id=uuid4(), name="enabled", is_enabled=True)
    model = _model(provider.id)
    sync_session.add_all([provider, model])
    sync_session.flush()
    sync_session.execute(
        update(Model)
        .execution_options(synchronize_session=False)
        .where(Model.id == model.id)
        .values(model_name="changed")
    )
    sync_session.execute(
        update(Provider)
        .execution_options(synchronize_session=False)
        .where(Provider.id == provider.id)
        .values(is_enabled=False)
    )
    assert model.model_name == "stored-model" and provider.is_enabled

    stale = await QueryService.get_model(session, Types.GetModelCommand(model.id))
    assert stale is not None and stale.model_name == "stored-model"
    refreshed = await QueryService.get_model(
        session, Types.GetModelCommand(model_id=model.id, refresh=True)
    )
    assert refreshed is not None and refreshed.model_name == "changed"
    session.get.assert_awaited_with(Model, model.id, populate_existing=True)
    provider_info = await QueryService.get_provider(
        session, Types.GetProviderCommand(provider_id=provider.id, refresh=True)
    )
    assert provider_info is not None and not provider_info.is_enabled
    session.get.assert_awaited_with(Provider, provider.id, populate_existing=True)
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_candidate_refresh_does_not_reuse_cached_enabled_model(
    model_database: tuple[Session, AsyncMock],
) -> None:
    sync_session, session = model_database
    provider = Provider(id=uuid4(), name="enabled", is_enabled=True)
    model = _model(provider.id)
    sync_session.add_all([provider, model])
    sync_session.flush()
    sync_session.execute(
        update(Model)
        .execution_options(synchronize_session=False)
        .where(Model.id == model.id)
        .values(is_enabled=False)
    )
    assert model.is_enabled
    stale = await QueryService.list_candidate_models(session)
    assert stale[0].is_enabled
    refreshed = await QueryService.list_candidate_models(
        session, Types.ListCandidateModelsCommand(refresh=True)
    )
    assert len(refreshed) == 1 and not refreshed[0].is_enabled
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_replacement_lookup_matches_all_three_ids(
    model_database: tuple[Session, AsyncMock],
) -> None:
    sync_session, session = model_database
    snapshot_id, from_id, to_id = uuid4(), uuid4(), uuid4()
    assert (
        await Repository.get_model_replacement(session, snapshot_id, from_id, to_id)
        is None
    )
    replacements = [
        ModelReplacement(
            id=uuid4(),
            product_snapshot_id=snapshot,
            from_model_id=source,
            to_model_id=target,
            reasoning_effort="low",
            effective_at=NOW,
        )
        for snapshot, source, target in (
            (snapshot_id, from_id, to_id),
            (uuid4(), from_id, to_id),
            (snapshot_id, uuid4(), to_id),
            (snapshot_id, from_id, uuid4()),
        )
    ]
    sync_session.add_all(replacements)
    sync_session.flush()
    entity = await Repository.get_model_replacement(
        session=session, snapshot_id=snapshot_id, from_id=from_id, to_id=to_id
    )
    assert entity is replacements[0]
    assert PersistenceMapper.model_replacement_entity_to_exists(entity)
    assert not PersistenceMapper.model_replacement_entity_to_exists(None)


@pytest.mark.asyncio
async def test_replacement_creation_flushes_without_ending_transaction() -> None:
    session = AsyncMock(spec=AsyncSession)
    snapshot_id, from_id, to_id = uuid4(), uuid4(), uuid4()
    await Repository.create_model_replacement(
        session=session,
        snapshot_id=snapshot_id,
        from_id=from_id,
        to_id=to_id,
        effort="custom-stored-effort",
        effective_at=NOW,
    )
    session.add.assert_called_once()
    entity = session.add.call_args.args[0]
    assert isinstance(entity, ModelReplacement)
    assert (entity.product_snapshot_id, entity.from_model_id, entity.to_model_id) == (
        snapshot_id,
        from_id,
        to_id,
    )
    assert entity.reasoning_effort == "custom-stored-effort"
    assert entity.effective_at == NOW
    session.flush.assert_awaited_once_with()
    session.commit.assert_not_awaited()
    session.rollback.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("exists", [False, True])
async def test_retirement_update_locks_and_preserves_missing_behavior(
    exists: bool,
) -> None:
    session = AsyncMock(spec=AsyncSession)
    entity = _model(uuid4())
    session.get.return_value = entity if exists else None
    shutdown_at = NOW + timedelta(days=1)
    updated = await Repository.set_model_retirement(
        session=session,
        model_id=entity.id,
        announced_at=NOW,
        shutdown_at=shutdown_at,
    )
    assert updated is (entity if exists else None)
    session.get.assert_awaited_once_with(Model, entity.id, with_for_update=True)
    if exists:
        assert (entity.retirement_announced_at, entity.shutdown_at) == (
            NOW,
            shutdown_at,
        )
        session.flush.assert_awaited_once_with()
    else:
        session.flush.assert_not_awaited()
    session.commit.assert_not_awaited()
    session.rollback.assert_not_awaited()


@pytest.mark.parametrize("retired", [False, True])
def test_mapper_fields_nullability_and_nested_capabilities_are_detached(
    retired: bool,
) -> None:
    entity = _model(uuid4())
    entity.is_enabled = False
    entity.retirement_announced_at = NOW if retired else None
    entity.shutdown_at = NOW + timedelta(days=1) if retired else None
    info = assert_type(PersistenceMapper.model_entity_to_info(entity), Types.ModelInfo)
    assert info == Types.ModelInfo(
        id=entity.id,
        provider_id=entity.provider_id,
        model_name="stored-model",
        is_enabled=False,
        capabilities={"reasoning_efforts": ["low"], "nested": {"values": [1]}},
        retirement_announced_at=entity.retirement_announced_at,
        shutdown_at=entity.shutdown_at,
        context_window=32000,
    )
    nested = info.capabilities["nested"]
    assert isinstance(nested, dict)
    values = nested["values"]
    assert isinstance(values, list)
    values.append(2)
    stored_nested = entity.capabilities["nested"]
    assert isinstance(stored_nested, dict)
    assert stored_nested["values"] == [1]
    stored_efforts = entity.capabilities["reasoning_efforts"]
    assert isinstance(stored_efforts, list)
    stored_efforts.append("high")
    assert info.capabilities["reasoning_efforts"] == ["low"]
    provider = Provider(id=entity.provider_id, name="StoredProvider", is_enabled=False)
    assert assert_type(
        PersistenceMapper.provider_entity_to_info(provider), Types.ProviderInfo
    ) == Types.ProviderInfo(provider.id, "StoredProvider", False)
    assert assert_type(PersistenceMapper.model_entity_to_info(None), None) is None
    assert assert_type(PersistenceMapper.provider_entity_to_info(None), None) is None
    assert PersistenceMapper.models_entities_to_info(iter(())) == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "state,message",
    [
        ("available", None),
        ("future_shutdown", None),
        ("custom_effort", None),
        ("model_missing", "Model is unavailable."),
        ("model_disabled", "Model is unavailable."),
        ("provider_missing", "Model is unavailable."),
        ("provider_disabled", "Model is unavailable."),
        ("shutdown_now", "Model is unavailable."),
        ("shutdown_past", "Model is unavailable."),
        ("unsupported_effort", "Model does not support this reasoning effort."),
        ("missing_efforts", "Model does not support this reasoning effort."),
    ],
)
async def test_model_validation_preserves_availability_effort_and_error_contracts(
    monkeypatch: pytest.MonkeyPatch, state: str, message: str | None
) -> None:
    clock = Mock(wraps=datetime)
    clock.now.return_value = NOW
    monkeypatch.setattr(QueryService, "datetime", clock)
    session = AsyncMock(spec=AsyncSession)
    entity = _model(uuid4())
    provider = Provider(id=entity.provider_id, name="offline", is_enabled=True)
    effort = "low"
    if state == "model_disabled":
        entity.is_enabled = False
    elif state == "provider_disabled":
        provider.is_enabled = False
    elif state == "shutdown_now":
        entity.shutdown_at = NOW
    elif state == "shutdown_past":
        entity.shutdown_at = NOW - timedelta(microseconds=1)
    elif state == "future_shutdown":
        entity.shutdown_at = NOW + timedelta(microseconds=1)
    elif state == "unsupported_effort":
        effort = "high"
    elif state == "missing_efforts":
        entity.capabilities = {}
    elif state == "custom_effort":
        effort = "custom-stored-effort"
        entity.capabilities = {"reasoning_efforts": [effort]}
    session.get.side_effect = [
        None if state == "model_missing" else entity,
        None if state == "provider_missing" else provider,
    ]
    command = Types.ValidateModelCommand(entity.id, effort)
    if message is None:
        info = await QueryService.validate_model(session=session, command=command)
        assert info == PersistenceMapper.model_entity_to_info(entity)
    else:
        with pytest.raises(ValueError) as error:
            await QueryService.validate_model(session, command)
        assert str(error.value) == message
    session.get.assert_any_await(Model, entity.id)
    if state == "model_missing":
        assert session.get.await_count == 1
    else:
        session.get.assert_any_await(Provider, provider.id)
    session.commit.assert_not_awaited()
    session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_query_does_not_hide_storage_errors() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.get.side_effect = RuntimeError("storage unavailable")
    with pytest.raises(RuntimeError, match="^storage unavailable$"):
        await QueryService.get_model(session, Types.GetModelCommand(uuid4()))
    session.scalars.side_effect = RuntimeError("storage unavailable")
    with pytest.raises(RuntimeError, match="^storage unavailable$"):
        await QueryService.list_candidate_models(session)
