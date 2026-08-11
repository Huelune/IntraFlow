from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from intraflow.models import (
    Assignment,
    AssignmentProgress,
    Device,
    Part,
    ProgressHistory,
    Project,
    SyncOutbox,
    Unit,
    User,
    WorkItem,
)
from intraflow.services.errors import PermissionDeniedError, ValidationError
from intraflow.services.progress_service import ProgressService
from intraflow.timeutil import utc_now_iso


def seed_assignment(session_factory: sessionmaker[Session]) -> tuple[str, str, str]:
    user_id = str(uuid4())
    device_id = str(uuid4())
    project_id = str(uuid4())
    part_id = str(uuid4())
    unit_id = str(uuid4())
    work_item_id = str(uuid4())
    assignment_id = str(uuid4())
    now = utc_now_iso()

    with session_factory.begin() as session:
        # Explicit flush boundaries mirror the domain creation order and keep FK behavior deterministic.
        session.add(User(
            id=user_id,
            user_code="tester",
            display_name="Tester",
            is_system_admin=0,
            is_active=1,
            created_at=now,
            updated_at=now,
            revision=1,
        ))
        session.flush()

        session.add_all([
            Device(
                id=device_id,
                user_id=user_id,
                device_name="TEST-PC",
                is_current=1,
                created_at=now,
            ),
            Project(
                id=project_id,
                name="Test Project",
                status="ACTIVE",
                revision=1,
                is_deleted=0,
                created_at=now,
                updated_at=now,
                updated_by=user_id,
            ),
            Unit(
                id=unit_id,
                code="TC",
                display_name="TC",
                is_active=1,
                sort_order=0,
            ),
        ])
        session.flush()

        session.add(Part(
            id=part_id,
            project_id=project_id,
            name="Part A",
            weight=1.0,
            sort_order=0,
            is_deleted=0,
            created_at=now,
            updated_at=now,
        ))
        session.flush()

        session.add(WorkItem(
            id=work_item_id,
            part_id=part_id,
            name="Test Execution",
            total_quantity=50,
            unit_id=unit_id,
            weight=1.0,
            sort_order=0,
            is_deleted=0,
            created_at=now,
            updated_at=now,
        ))
        session.flush()

        session.add(Assignment(
            id=assignment_id,
            work_item_id=work_item_id,
            user_id=user_id,
            allocated_quantity=50,
            status="ACTIVE",
            is_deleted=0,
            created_at=now,
            updated_at=now,
        ))

    return assignment_id, user_id, device_id


def test_add_delta_updates_progress_history_and_outbox(session_factory: sessionmaker[Session]) -> None:
    assignment_id, user_id, device_id = seed_assignment(session_factory)
    service = ProgressService(
        session_factory,
        current_user_id=user_id,
        current_device_id=device_id,
    )

    first = service.add_delta(assignment_id, 5, "첫 진행")
    second = service.add_delta(assignment_id, 3)

    assert first.current_quantity == 5
    assert second.previous_quantity == 5
    assert second.current_quantity == 8
    assert second.progress_ratio == pytest.approx(0.16)

    with session_factory() as session:
        progress = session.get(AssignmentProgress, assignment_id)
        histories = list(session.scalars(
            select(ProgressHistory)
            .where(ProgressHistory.assignment_id == assignment_id)
            .order_by(ProgressHistory.created_at)
        ))
        outboxes = list(session.scalars(select(SyncOutbox)))

    assert progress is not None
    assert progress.completed_quantity == 8
    assert progress.note == "첫 진행"
    assert len(histories) == 2
    assert histories[0].delta_quantity == 5
    assert histories[1].delta_quantity == 3
    assert len(outboxes) == 1
    assert outboxes[0].target_type == "USER_PUBLIC"
    assert outboxes[0].target_id == user_id


def test_progress_cannot_exceed_allocation(session_factory: sessionmaker[Session]) -> None:
    assignment_id, user_id, device_id = seed_assignment(session_factory)
    service = ProgressService(session_factory, current_user_id=user_id, current_device_id=device_id)

    with pytest.raises(ValidationError):
        service.add_delta(assignment_id, 51)

    with session_factory() as session:
        assert session.get(AssignmentProgress, assignment_id) is None
        assert list(session.scalars(select(ProgressHistory))) == []
        assert list(session.scalars(select(SyncOutbox))) == []


def test_only_assignee_can_update(session_factory: sessionmaker[Session]) -> None:
    assignment_id, _user_id, device_id = seed_assignment(session_factory)
    other_user_id = str(uuid4())
    now = utc_now_iso()

    with session_factory.begin() as session:
        session.add(User(
            id=other_user_id,
            user_code="other",
            display_name="Other",
            is_system_admin=1,
            is_active=1,
            created_at=now,
            updated_at=now,
            revision=1,
        ))

    service = ProgressService(
        session_factory,
        current_user_id=other_user_id,
        current_device_id=device_id,
    )

    with pytest.raises(PermissionDeniedError):
        service.add_delta(assignment_id, 1)
