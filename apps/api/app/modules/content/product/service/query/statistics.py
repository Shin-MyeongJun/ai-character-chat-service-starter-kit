# 소유 상품과 선택 버전 소속을 확인한다. 조회 날짜는 양 끝 포함, 최대 731일이다.
# 집계가 없는 날짜를 만들어 채우지 않으며 pending_days로 재집계 대기를 표시한다.
from app.modules.content.product import repository as Repository
from app.modules.content.product import types as Types
from app.modules.content.product.mapper import statistics as StatisticsMapper
from app.modules.content.product.service import query as QueryService


async def get_statistics(
    session, command: Types.GetStatisticsCommand
) -> Types.StatisticsInfo:
    product_id = command.product_id
    owner_id = command.owner_id
    date_from = command.date_from
    date_to = command.date_to
    snapshot_id = command.snapshot_id
    if date_to < date_from or (date_to - date_from).days > 730:
        raise ValueError("Statistics range must be ordered and at most 731 days.")
    await QueryService.get_owned_product(
        session, Types.OwnedProductCommand(product_id, owner_id)
    )
    if snapshot_id is not None:
        snapshot = await QueryService.get_product_snapshot(
            session, Types.ProductSnapshotCommand(snapshot_id)
        )
        if snapshot.product_id != product_id:
            raise LookupError("Version not found.")
    row = await Repository.get_statistics_report(
        session, product_id, date_from, date_to, snapshot_id
    )
    return StatisticsMapper.statistics_report_row_to_info(
        row, product_id, snapshot_id, date_from, date_to
    )
