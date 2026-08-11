from __future__ import annotations

import pytest
from sqlalchemy.orm import Session, sessionmaker

from intraflow.services.errors import PermissionDeniedError, ValidationError
from intraflow.services.setup_service import SetupService
from intraflow.services.work_service import WorkService

from workflow import build_workflow


def test_owner_can_update_and_delete_work(session_factory: sessionmaker[Session]) -> None:
    _identity, _admin, work, _project, _part, item = build_workflow(session_factory)
    work.update_my_work_item(item.work_item_id, "수정 업무", "수정", 20, item.unit_id, 1,
                             "2026-08-03", "2026-08-21")
    updated = work.get_my_work_item(item.work_item_id)
    assert updated.name == "수정 업무"
    assert updated.total_quantity == 20
    work.delete_my_work_item(item.work_item_id)
    assert work.list_my_work_items(include_inactive=True) == []


def test_admin_cannot_modify_another_users_work(session_factory: sessionmaker[Session]) -> None:
    _identity, admin, _work, _project, _part, item = build_workflow(session_factory)
    admin_id = admin.create_user("admin2", "Admin2", is_system_admin=True)
    other = WorkService(session_factory, current_user_id=admin_id)
    with pytest.raises(PermissionDeniedError):
        other.set_my_work_item_active(item.work_item_id, False)


def test_work_period_and_total_are_validated(session_factory: sessionmaker[Session]) -> None:
    identity, _admin, work, _project, _part, item = build_workflow(session_factory)
    with pytest.raises(ValidationError, match="상위 파트"):
        work.update_my_work_item(item.work_item_id, item.name, None, 10, item.unit_id, 1,
                                 "2026-07-01", "2026-08-10")
    assert identity.user_id
