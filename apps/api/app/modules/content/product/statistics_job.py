# 외부 스케줄러가 호출하는 일회 실행 진입점이다. 이 파일 자체는 주기 실행을 등록하지 않는다.
# --repair-recent는 최근 일자 재집계 요청을 추가하고, --limit만큼 큐를 처리한 뒤 종료한다.
"""Run hourly; pass --repair-recent nightly. DATABASE_URL comes from deployment."""

import argparse
import asyncio
import os

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.modules.content.product import types as Types
from app.use_cases.product_statistics import (
    enqueue_recent,
    process_pending,
)


async def run(limit, repair):
    engine = create_async_engine(os.environ["DATABASE_URL"])
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            if repair:
                await enqueue_recent(session, Types.EnqueueRecentCommand())
            count = await process_pending(
                session, Types.ProcessPendingCommand(limit=limit)
            )
            print(f"Processed {count.processed} product statistic days.")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--repair-recent", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(args.limit, args.repair_recent))
