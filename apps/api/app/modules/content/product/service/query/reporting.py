"""기존 통계 소유권을 유지하는 소유자·관리자별 읽기 경계."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.reporting import get_reporting_period
from app.modules.content.product import types as Types
from app.modules.content.product.mapper import reporting as ReportingPersistenceMapper
from app.modules.content.product.repository import reporting as ReportingRepository
from app.modules.content.product.service import query as QueryService
from app.modules.identity import types as IdentityTypes
from app.modules.identity.service import query as IdentityQueryService


async def _read_product_statistics(
    session: AsyncSession, command: Types.GetReportingStatisticsCommand
) -> Types.ReportingStatisticsInfo:
    """작품에 속한 버전만 조회한 뒤 집계 존재·중복 제거 결과를 변환한다."""
    if command.snapshot_id is not None:
        snapshot = await QueryService.get_product_snapshot(
            session, Types.ProductSnapshotCommand(snapshot_id=command.snapshot_id)
        )
        if snapshot.product_id != command.product_id:
            raise LookupError("Version not found.")
    row = await ReportingRepository.get_product_reporting_statistics(
        session,
        command.product_id,
        command.date_from,
        command.date_to,
        command.snapshot_id,
    )
    return ReportingPersistenceMapper.product_reporting_row_to_info(row, command)


async def get_owner_reporting_statistics(
    session: AsyncSession, command: Types.GetReportingStatisticsCommand
) -> Types.ReportingStatisticsInfo:
    """활성 소유자에게만 작품·버전 집계를 읽기 전용으로 제공한다."""
    get_reporting_period(command.date_from, command.date_to)
    with session.no_autoflush:
        await IdentityQueryService.require_active_user(
            session, IdentityTypes.GetUserCommand(user_id=command.actor_id)
        )
        await QueryService.get_owned_product(
            session,
            Types.OwnedProductCommand(
                product_id=command.product_id, owner_id=command.actor_id
            ),
        )
        return await _read_product_statistics(session, command)


async def get_admin_reporting_statistics(
    session: AsyncSession, command: Types.GetReportingStatisticsCommand
) -> Types.ReportingStatisticsInfo:
    """활성 관리자에게 비공개 작품을 포함한 기존 사용량 집계를 제공한다."""
    get_reporting_period(command.date_from, command.date_to)
    with session.no_autoflush:
        await IdentityQueryService.require_admin(
            session, IdentityTypes.GetUserCommand(user_id=command.actor_id)
        )
        product = await QueryService.get_product_state(
            session, Types.GetProductStateCommand(product_id=command.product_id)
        )
        if product is None:
            raise LookupError("Product not found.")
        return await _read_product_statistics(session, command)


async def get_recorded_service_statistics(
    session: AsyncSession, command: Types.GetServiceReportingStatisticsCommand
) -> Types.ServiceReportingStatisticsInfo:
    """관리자에게 기록된 작품 통계 합계만 제공하며 전체 서비스 커버리지는 확정하지 않는다."""
    get_reporting_period(command.date_from, command.date_to)
    with session.no_autoflush:
        await IdentityQueryService.require_admin(
            session, IdentityTypes.GetUserCommand(user_id=command.actor_id)
        )
        row = await ReportingRepository.get_service_reporting_statistics(
            session, command.date_from, command.date_to
        )
        return ReportingPersistenceMapper.service_reporting_row_to_info(row)


async def get_statistics_queue(
    session: AsyncSession, command: Types.GetStatisticsQueueCommand
) -> Types.StatisticsQueueInfo:
    """관리자가 전체 대기 현황을 확인하며 claim·삭제·재집계를 실행하지 않는다."""
    with session.no_autoflush:
        await IdentityQueryService.require_admin(
            session, IdentityTypes.GetUserCommand(user_id=command.actor_id)
        )
        row = await ReportingRepository.get_statistics_queue(session)
        return ReportingPersistenceMapper.statistics_queue_row_to_info(row)
