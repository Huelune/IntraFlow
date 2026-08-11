from __future__ import annotations

import pytest
from sqlalchemy.orm import Session, sessionmaker

from intraflow.services.administration_service import AdministrationService
from intraflow.services.errors import ValidationError
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
