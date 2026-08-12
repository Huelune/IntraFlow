from __future__ import annotations

import pytest
from sqlalchemy.orm import Session, sessionmaker

from intraflow.services.administration_service import AdministrationService
from intraflow.services.errors import PermissionDeniedError, ValidationError
from intraflow.services.setup_service import SetupService

from workflow import build_workflow


def test_admin_manages_project_and_part_periods(session_factory: sessionmaker[Session]) -> None:
    identity, admin, _work, project_id, part_id, _item = build_workflow(session_factory)
    assert admin.current_permissions() == (True, True)
    admin.set_part_active(part_id, False)
    admin.set_project_active(project_id, False)
    assert admin.list_parts()[0].is_active == 0
    assert admin.list_projects()[0].status == "INACTIVE"
    assert identity.user_id


def test_part_must_stay_within_project_period(session_factory: sessionmaker[Session]) -> None:
    identity = SetupService(session_factory).provision("owner", "Owner", "PC")
    admin = AdministrationService(session_factory, current_user_id=identity.user_id)
    project_id = admin.create_project("프로젝트", "2026-08-01", "2026-08-31")
    with pytest.raises(ValidationError, match="상위 기간"):
        admin.create_part(project_id, "파트", 1, "2026-07-31", "2026-08-10")


def test_system_admin_can_manage_project_without_editor_role(session_factory: sessionmaker[Session]) -> None:
    _identity, admin, _work, project_id, _part_id, _item = build_workflow(session_factory)
    other_id = admin.create_user("other-admin", "Other Admin", is_system_admin=True)
    other = AdministrationService(session_factory, current_user_id=other_id)
    other.create_part(project_id, "추가 파트", 1, "2026-08-01", "2026-08-31")
    assert len(other.list_parts(project_id)) == 2


def test_admin_updates_user_unit_and_current_device(session_factory: sessionmaker[Session]) -> None:
    identity = SetupService(session_factory).provision("owner", "Owner", "PC-1")
    admin = AdministrationService(session_factory, current_user_id=identity.user_id)
    user_id = admin.create_user("member", "Member")
    first = admin.create_device(user_id, "PC-A", is_current=True)
    second = admin.create_device(user_id, "PC-B", is_current=True)
    unit_id = admin.create_unit("EA", "개")

    admin.update_user(user_id, "member-2", "Member 2", is_system_admin=False, is_active=True)
    admin.update_device(first, "PC-A2", is_current=True)
    admin.update_unit(unit_id, "ITEM", "항목", sort_order=2, is_active=False)

    users = {user.id: user for user in admin.list_users()}
    devices = {device.id: device for device in admin.list_devices(user_id)}
    units = {unit.id: unit for unit in admin.list_units()}
    assert users[user_id].user_code == "member-2"
    assert devices[first].device_name == "PC-A2"
    assert devices[first].is_current == 1
    assert devices[second].is_current == 0
    assert units[unit_id].code == "ITEM"
    assert units[unit_id].is_active == 0


def test_last_active_admin_cannot_lose_admin_permission(session_factory: sessionmaker[Session]) -> None:
    identity = SetupService(session_factory).provision("owner", "Owner", "PC")
    admin = AdministrationService(session_factory, current_user_id=identity.user_id)

    with pytest.raises(ValidationError, match="마지막 활성 시스템 관리자"):
        admin.update_user(identity.user_id, "owner", "Owner", is_system_admin=False, is_active=True)


def test_only_admin_replaces_project_editors(session_factory: sessionmaker[Session]) -> None:
    _identity, admin, _work, project_id, _part, _item = build_workflow(session_factory)
    editor_id = admin.create_user("editor", "Editor")
    admin.replace_project_editors(project_id, {editor_id})
    assert [user.id for user in admin.list_project_editors(project_id)] == [editor_id]

    editor = AdministrationService(session_factory, current_user_id=editor_id)
    editor.update_project(project_id, "수정 프로젝트", "2026-08-01", "2026-08-31")
    with pytest.raises(PermissionDeniedError):
        editor.replace_project_editors(project_id, {editor_id})
    with pytest.raises(ValidationError, match="한 명 이상"):
        admin.replace_project_editors(project_id, set())
