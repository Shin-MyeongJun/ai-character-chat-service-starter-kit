"""영역별 권한과 공개 도메인 조회를 조합한다. HTTP/DB 쓰기를 수행하지 않는다."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.reporting import get_reporting_period
from app.modules.content.product import types as ProductTypes
from app.modules.content.product.service.query import (
    reporting as ProductReportingQueryService,
)
from app.modules.identity import types as IdentityTypes
from app.modules.identity.service import query as IdentityQueryService
from app.modules.reporting.creator_reporting import types as Types
from app.modules.reporting.creator_reporting.mapper import (
    persistence as PersistenceMapper,
)


async def get_product_report(
    session: AsyncSession,
    command: Types.GetCreatorProductReportCommand,
    *,
    actor: Types.ActorCommand,
) -> Types.CreatorProductReportView:
    """활성 작가의 소유 작품 집계만 영역별 결과 타입으로 제공한다.

    product 공개 조회가 소유권/버전 소속을 확인하고 부모 일별 집계 유무를 반환한다.
    누락 날짜가 있거나 dirty 상태면 확정 totals는 없고 recorded_totals만 제공한다.
    """
    period = get_reporting_period(command.date_from, command.date_to)
    if (
        not isinstance(command.product_id, UUID)
        or command.snapshot_id is not None
        and not isinstance(command.snapshot_id, UUID)
    ):
        raise Types.ReportError("invalid_input")
    with session.no_autoflush:
        await _require_actor(session, actor)
        # 영역 권한 → 도메인 범위 검증 → 집계 존재/최신성 → 허용 필드 변환 순서다.
        try:
            info = await ProductReportingQueryService.get_owner_reporting_statistics(
                session,
                ProductTypes.GetReportingStatisticsCommand(
                    actor_id=actor.user_id,
                    product_id=command.product_id,
                    date_from=command.date_from,
                    date_to=command.date_to,
                    snapshot_id=command.snapshot_id,
                ),
            )
        except LookupError as exc:
            raise Types.ReportError("not_found") from exc
        return PersistenceMapper.product_statistics_info_to_view(
            info, period, datetime.now(UTC)
        )


async def _require_actor(session: AsyncSession, actor: Types.ActorCommand) -> None:
    """인증 경계의 ID로 최신 활성 사용자 상태를 확인한다."""
    if not isinstance(actor.user_id, UUID):
        raise Types.ReportError("invalid_input")
    try:
        await IdentityQueryService.require_active_user(
            session, IdentityTypes.GetUserCommand(user_id=actor.user_id)
        )
    except LookupError as exc:
        raise Types.ReportError("forbidden") from exc
