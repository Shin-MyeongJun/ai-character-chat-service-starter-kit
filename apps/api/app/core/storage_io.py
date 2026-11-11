"""Keep caller-owned streams and locks alive until storage operations settle."""

import asyncio
from collections.abc import Coroutine
from typing import TypeVar

TStorageResult = TypeVar("TStorageResult")


async def settle_storage_operation(
    operation: Coroutine[object, object, TStorageResult],
) -> TStorageResult:
    task = asyncio.create_task(operation)
    cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled = True
        except Exception:
            break
    if cancelled:
        # Retrieve any provider exception while preserving caller cancellation.
        try:
            task.result()
        finally:
            raise asyncio.CancelledError
    return task.result()
