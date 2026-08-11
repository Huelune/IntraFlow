from __future__ import annotations

import pytest
from sqlalchemy.orm import Session, sessionmaker

from intraflow.models import Assignment, ProjectEditor, User
from intraflow.services.administration_service import AdministrationService
from intraflow.services.errors import PermissionDeniedError, ValidationError
from intraflow.services.progress_service import ProgressService
from intraflow.services.setup_service import SetupService


def build_workflow(session_factory: sessionmaker[Session]):
    identity = SetupService(session_factory).provision("owner", "Owner", "OWNER-PC")
    admin = AdministrationService(session_factory, current_user_id=identity.user_id)
    unit_id = admin.create_unit("EA", "개")
    project_id = admin.create_project("첫 프로젝트", "2026-08-01", "2026-08-31")
    part_id = admin.create_part(project_id, "설계", 1.0)
    work_id = admin.create_work_item(part_id, "기본 설계", 10, unit_id, 1.0)
    assignment_id = admin.create_assignment(work_id, identity.user_id, 10)
    return identity, admin, project_id, assignment_id


def test_admin_can_create_complete_assignment_workflow(session_factory: sessionmaker[Session]) -> None:
    identity, admin, project_id, assignment_id = build_workflow(session_factory)

    with session_factory() as session:
        user = session.get(User, identity.user_id)
        editor = session.get(ProjectEditor, (project_id, identity.user_id))
        assignment = session.get(Assignment, assignment_id)
    assert user is not None and user.is_system_admin == 1
    assert editor is not None
    assert assignment is not None and assignment.status == "ACTIVE"
    assert admin.current_permissions() == (True, True)


def test_duplicate_assignment_is_rejected(session_factory: sessionmaker[Session]) -> None:
    identity, admin, _project_id, assignment_id = build_workflow(session_factory)
    work_item_id = admin.list_assignments()[0].work_item_id

    with pytest.raises(ValidationError):
        admin.create_assignment(work_item_id, identity.user_id, 1)
    assert assignment_id


def test_assignment_with_history_is_cancelled_not_deleted(session_factory: sessionmaker[Session]) -> None:
    identity, admin, _project_id, assignment_id = build_workflow(session_factory)
    ProgressService(
        session_factory, current_user_id=identity.user_id, current_device_id=identity.device_id,
    ).add_delta(assignment_id, 1)

    admin.cancel_assignment(assignment_id)

    with session_factory() as session:
        assignment = session.get(Assignment, assignment_id)
    assert assignment is not None
    assert assignment.status == "CANCELLED"
    assert assignment.is_deleted == 0


def test_assignment_quantity_cannot_drop_below_completed_progress(session_factory: sessionmaker[Session]) -> None:
    identity, admin, _project_id, assignment_id = build_workflow(session_factory)
    ProgressService(
        session_factory, current_user_id=identity.user_id, current_device_id=identity.device_id,
    ).add_delta(assignment_id, 4)

    with pytest.raises(ValidationError):
        admin.update_assignment_quantity(assignment_id, 3)
    admin.update_assignment_quantity(assignment_id, 5)

    with session_factory() as session:
        assignment = session.get(Assignment, assignment_id)
    assert assignment is not None and assignment.allocated_quantity == 5


def test_system_admin_without_editor_role_cannot_edit_project(session_factory: sessionmaker[Session]) -> None:
    _identity, admin, project_id, _assignment_id = build_workflow(session_factory)
    other_id = admin.create_user("other-admin", "Other Admin", is_system_admin=True)
    other = AdministrationService(session_factory, current_user_id=other_id)

    with pytest.raises(PermissionDeniedError):
        other.create_part(project_id, "Unauthorized", 1.0)
