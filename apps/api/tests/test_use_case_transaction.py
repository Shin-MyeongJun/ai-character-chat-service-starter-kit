from uuid import uuid4

import pytest
from app.db.models.identity import User
from app.db.transaction import use_case_transaction
from sqlalchemy import event, select
from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_nested_scopes_commit_once_at_the_outer_boundary(db):
    commits = []
    event.listen(db.sync_session, "after_commit", lambda _: commits.append(True))
    user_id = uuid4()
    async with use_case_transaction(db):
        db.add(User(id=user_id, email=f"{user_id}@test.invalid"))
        async with use_case_transaction(db):
            await db.flush()
        assert commits == []
        async with AsyncSession(db.bind) as observer:
            assert await observer.get(User, user_id) is None
    assert commits == [True]
    async with AsyncSession(db.bind) as observer:
        assert await observer.get(User, user_id) is not None


@pytest.mark.asyncio
async def test_caught_nested_failure_still_rolls_back_all_writes(db):
    user_id = uuid4()
    with pytest.raises(RuntimeError, match="nested use case failed"):
        async with use_case_transaction(db):
            db.add(User(id=user_id, email=f"{user_id}@test.invalid"))
            await db.flush()
            try:
                async with use_case_transaction(db):
                    raise ValueError("Dependent command failed")
            except ValueError:
                pass
    assert not db.in_transaction()
    async with AsyncSession(db.bind) as observer:
        assert await observer.get(User, user_id) is None
    # The failed scope must not poison a later independent use case.
    async with use_case_transaction(db):
        db.add(User(id=user_id, email=f"{user_id}@test.invalid"))


@pytest.mark.asyncio
async def test_unrelated_autobegun_transaction_is_not_committed_or_adopted(db):
    await db.execute(select(User.id))
    with pytest.raises(InvalidRequestError):
        async with use_case_transaction(db):
            pytest.fail("An unrelated transaction must not be adopted")
    assert db.in_transaction()
    await db.rollback()
