from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from intraflow.models import AssignmentProgress, ProgressHistory, SyncOutbox
from intraflow.services.errors import PermissionDeniedError, ValidationError
from intraflow.services.progress_service import ProgressService
from intraflow.services.setup_service import SetupService

from workflow import build_workflow


def test_progress_quantity_note_schedule_and_history(session_factory: sessionmaker[Session]) -> None:
    identity, _admin, _work, _project, _part, item = build_workflow(session_factory)
    service = ProgressService(session_factory, current_user_id=identity.user_id, current_device_id=identity.device_id)
    service.add_delta(item.assignment_id, 3, "시작")
    service.set_completed_quantity(item.assignment_id, 5)
    service.set_note(item.assignment_id, "현재 메모")
    service.set_schedule(item.assignment_id, "2026-08-03", "2026-08-10")
    with session_factory() as session:
        progress = session.get(AssignmentProgress, item.assignment_id)
        histories = list(session.scalars(select(ProgressHistory).where(
            ProgressHistory.assignment_id == item.assignment_id)))
        outboxes = list(session.scalars(select(SyncOutbox).where(SyncOutbox.target_type == "USER_PUBLIC")))
    assert progress is not None and progress.completed_quantity == 5
    assert progress.note == "현재 메모"
    assert progress.schedule_start == "2026-08-03"
    assert len(histories) == 3
    assert len(outboxes) == 1


def test_progress_rejects_over_target_and_other_user(session_factory: sessionmaker[Session]) -> None:
    identity, admin, _work, _project, _part, item = build_workflow(session_factory)
    service = ProgressService(session_factory, current_user_id=identity.user_id, current_device_id=identity.device_id)
    with pytest.raises(ValidationError):
        service.add_delta(item.assignment_id, 11)
    other_id = admin.create_user("other", "Other")
    other = ProgressService(session_factory, current_user_id=other_id, current_device_id=None)
    assert len(other.list_public_history(item.assignment_id)) == 0
    with pytest.raises(PermissionDeniedError):
        other.add_delta(item.assignment_id, 1)


def test_other_active_user_can_read_public_history_only(session_factory: sessionmaker[Session]) -> None:
    identity, admin, _work, _project, _part, item = build_workflow(session_factory)
    owner = ProgressService(session_factory, current_user_id=identity.user_id, current_device_id=identity.device_id)
    owner.add_delta(item.assignment_id, 2, "공개 메모")
    other_id = admin.create_user("viewer", "Viewer")
    viewer = ProgressService(session_factory, current_user_id=other_id, current_device_id=None)

    history = viewer.list_public_history(item.assignment_id)

    assert len(history) == 1
    assert history[0].note == "공개 메모"
    with pytest.raises(PermissionDeniedError):
        viewer.set_note(item.assignment_id, "변조")


def test_inactive_parent_blocks_progress(session_factory: sessionmaker[Session]) -> None:
    identity, admin, _work, project_id, _part, item = build_workflow(session_factory)
    admin.set_project_active(project_id, False)
    service = ProgressService(session_factory, current_user_id=identity.user_id, current_device_id=identity.device_id)
    with pytest.raises(ValidationError, match="비활성"):
        service.add_delta(item.assignment_id, 1)
