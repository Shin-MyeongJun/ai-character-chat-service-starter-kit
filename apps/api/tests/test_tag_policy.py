"""Value-only contracts shared by all content tag callers."""

from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.modules.content.tag import types as TagTypes
from app.modules.content.tag.service import policy as TagPolicyService


ADMIN_ID, SYSTEM_ID, NEW_ID = (UUID(int=i) for i in range(1, 4))
NOW = datetime(2026, 10, 30, tzinfo=UTC)
LINKS = (
    TagTypes.InternalTagLinkInfo(ADMIN_ID, "admin", None, NOW, NOW),
    TagTypes.InternalTagLinkInfo(SYSTEM_ID, "system", None, NOW, NOW),
)


@pytest.mark.parametrize(
    ("append", "requested", "expected"),
    [
        (True, (SYSTEM_ID, NEW_ID, NEW_ID), (ADMIN_ID, SYSTEM_ID, NEW_ID)),
        (True, (), (ADMIN_ID, SYSTEM_ID)),
        (False, (SYSTEM_ID, ADMIN_ID), (SYSTEM_ID, ADMIN_ID)),
        (False, (), ()),
    ],
)
def test_public_order_and_clear(append, requested, expected):
    command = TagTypes.SelectPublicTagIdsCommand(
        retained_ids=(ADMIN_ID, SYSTEM_ID), requested_ids=requested, append=append
    )
    assert TagPolicyService.select_public_tag_ids(command) == expected
    assert command.retained_ids == (ADMIN_ID, SYSTEM_ID)
    assert command.requested_ids == requested


@pytest.mark.parametrize(
    ("source", "replace", "requested", "removed", "assigned"),
    [
        ("admin", False, (SYSTEM_ID, ADMIN_ID, NEW_ID), (), (SYSTEM_ID, ADMIN_ID, NEW_ID)),
        ("system", False, (ADMIN_ID, SYSTEM_ID, NEW_ID), (), (SYSTEM_ID, NEW_ID)),
        ("admin", True, (NEW_ID, SYSTEM_ID), (ADMIN_ID,), (NEW_ID, SYSTEM_ID)),
        ("admin", True, (), (ADMIN_ID, SYSTEM_ID), ()),
        ("system", False, (), (), ()),
        ("system", True, (), (SYSTEM_ID,), ()),
    ],
)
def test_internal_selection_protection_takeover_and_clear(
    source, replace, requested, removed, assigned
):
    command = TagTypes.PlanInternalTagChangesCommand(
        links=LINKS, requested_ids=requested, source=source, replace=replace
    )
    changes = TagPolicyService.plan_internal_tag_changes(command)
    assert changes.remove_ids == removed
    assert changes.set_ids == assigned
    assert command.links == LINKS
    assert command.requested_ids == requested


@pytest.mark.parametrize("source", ["admin", "system"])
@pytest.mark.parametrize("tag_id", [ADMIN_ID, SYSTEM_ID, NEW_ID])
def test_internal_removal_protection_and_missing_link_idempotency(source, tag_id):
    command = TagTypes.ValidateInternalTagRemovalCommand(
        links=LINKS, tag_id=tag_id, source=source
    )
    if source == "system" and tag_id == ADMIN_ID:
        with pytest.raises(
            ValueError, match="System cannot remove an administrator-assigned tag."
        ):
            TagPolicyService.validate_internal_tag_removal(command)
    else:
        assert TagPolicyService.validate_internal_tag_removal(command) is None
