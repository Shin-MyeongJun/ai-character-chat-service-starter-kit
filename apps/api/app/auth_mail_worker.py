"""Run separately from the API: python -m app.auth_mail_worker [--once]."""

import argparse
import asyncio
import logging
import os

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.modules.identity.adapters import SMTPMailSender
from app.modules.identity.service import (
    AuthenticationMailWorkflow,
    AuthenticationService,
)
from app.modules.identity.settings import load_auth_settings


async def run_worker(*, once: bool) -> None:
    settings = load_auth_settings()
    # Never print SQL parameter values, including encrypted bearer material.
    engine = create_async_engine(os.environ["DATABASE_URL"], hide_parameters=True)
    try:
        authentication = AuthenticationService(
            async_sessionmaker(engine, expire_on_commit=False), settings
        )
        workflow = AuthenticationMailWorkflow(authentication, SMTPMailSender(settings))
        while True:
            if not await workflow.deliver_next_mail():
                if once:
                    return
                await asyncio.sleep(1)
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--once", action="store_true", help="Drain currently due mail, then exit"
    )
    arguments = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(run_worker(once=arguments.once))
    except KeyboardInterrupt:
        return
    except Exception as exc:
        # Provider exceptions may carry recipients or links in their text/chain.
        logging.getLogger(__name__).error(
            "auth_mail_worker stopped error_type=%s", type(exc).__name__
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
