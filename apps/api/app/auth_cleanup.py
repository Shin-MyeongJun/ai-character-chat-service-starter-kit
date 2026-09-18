"""인증 대기 계정·만료 증명·세션·제한 버킷 정리. 운영 스케줄러에서 매시간 실행한다."""

import asyncio
import os

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.modules.identity.adapters import SMTPMailSender
from app.modules.identity.service import AuthenticationService
from app.modules.identity.settings import load_auth_settings


async def main():
    engine = create_async_engine(os.environ["DATABASE_URL"])
    try:
        settings = load_auth_settings()
        service = AuthenticationService(
            async_sessionmaker(engine, expire_on_commit=False),
            settings,
            SMTPMailSender(settings),
        )
        # 개인정보/토큰을 출력하지 않고 처리 건수만 보고한다.
        print(await service.cleanup_expired_auth())
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
