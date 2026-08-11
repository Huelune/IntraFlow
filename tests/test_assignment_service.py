from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from intraflow.services.assignment_service import AssignmentService
from intraflow.services.progress_service import ProgressService

from test_progress_service import seed_assignment


def test_list_active_assignments_includes_derived_progress(session_factory: sessionmaker[Session]) -> None:
    assignment_id, user_id, device_id = seed_assignment(session_factory)
    ProgressService(session_factory, current_user_id=user_id, current_device_id=device_id).add_delta(assignment_id, 10)

    assignments = AssignmentService(session_factory, current_user_id=user_id).list_active()

    assert len(assignments) == 1
    assert assignments[0].assignment_id == assignment_id
    assert assignments[0].completed_quantity == 10
    assert assignments[0].allocated_quantity == 50
    assert assignments[0].progress_ratio == 0.2
