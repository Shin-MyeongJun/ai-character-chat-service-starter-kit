"""Execution dependencies shared by services; no ORM data crosses this boundary."""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import TypeAlias

from sqlalchemy.ext.asyncio import AsyncSession

# async_sessionmaker and contextmanager-based factories both satisfy this contract.
# Each call supplies a context that owns and closes its session. The factory itself
# is synchronous; callers use `async with session_factory()`, not `await factory()`.
SessionFactory: TypeAlias = Callable[[], AbstractAsyncContextManager[AsyncSession]]
