from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from intraflow.database import create_session_factory, create_sqlite_engine
from intraflow.models import AssignmentProgress, Base, CalendarEvent, PersonalNote, Project, SyncOutbox
from intraflow.services.progress_service import ProgressService
from intraflow.sync.nas_client import NasClient
from intraflow.sync.pull_service import PullService
from intraflow.sync.push_service import PushService
from intraflow.sync.snapshot_builder import SnapshotBuilder
from intraflow.sync.snapshot_validator import SnapshotValidator
from intraflow.timeutil import utc_now_iso

from test_progress_service import seed_assignment


def test_user_public_snapshot_excludes_private_data(session_factory: sessionmaker[Session]) -> None:
    assignment_id, user_id, device_id = seed_assignment(session_factory)
    ProgressService(session_factory, current_user_id=user_id, current_device_id=device_id).add_delta(assignment_id, 5)
    now = utc_now_iso()
    with session_factory.begin() as session:
        session.add_all([
            CalendarEvent(
                id="00000000-0000-4000-8000-000000000001",
                user_id=user_id,
                title="Team meeting",
                event_type="MEETING",
                start_at=now,
                visibility="TEAM",
                revision=1,
                is_deleted=0,
                created_at=now,
                updated_at=now,
            ),
            CalendarEvent(
                id="00000000-0000-4000-8000-000000000002",
                user_id=user_id,
                title="Private appointment",
                event_type="OTHER",
                start_at=now,
                visibility="PRIVATE",
                revision=1,
                is_deleted=0,
                created_at=now,
                updated_at=now,
            ),
            PersonalNote(
                id="00000000-0000-4000-8000-000000000003",
                user_id=user_id,
                title="Private note",
                is_pinned=0,
                is_deleted=0,
                created_at=now,
                updated_at=now,
            ),
        ])
    with session_factory() as session:
        snapshot = SnapshotBuilder(session).user_public(user_id)
    payload = snapshot.model_dump(mode="json")
    validated = SnapshotValidator().validate(payload)

    assert validated.user_id == user_id
    assert len(snapshot.progress) == 1
    assert [event.title for event in snapshot.team_calendar_events] == ["Team meeting"]
    assert "Private appointment" not in str(payload)
    assert "Private note" not in str(payload)


def test_user_public_push_writes_json_and_clears_outbox(
    session_factory: sessionmaker[Session], tmp_path
) -> None:
    assignment_id, user_id, device_id = seed_assignment(session_factory)
    ProgressService(session_factory, current_user_id=user_id, current_device_id=device_id).add_delta(assignment_id, 5)
    service = PushService(session_factory, NasClient(tmp_path / "nas"))

    revision = service.push_user_public(user_id)

    payload = NasClient(tmp_path / "nas").read_json("users", user_id, "public.json")
    assert payload is not None
    assert payload["source_type"] == "USER_PUBLIC"
    assert payload["revision"] == revision
    with session_factory() as session:
        assert list(session.scalars(select(SyncOutbox))) == []


def test_pull_applies_definition_then_read_only_user_progress(
    session_factory: sessionmaker[Session], tmp_path
) -> None:
    assignment_id, user_id, device_id = seed_assignment(session_factory)
    ProgressService(session_factory, current_user_id=user_id, current_device_id=device_id).add_delta(assignment_id, 5)
    nas = NasClient(tmp_path / "nas")
    with session_factory() as source:
        builder = SnapshotBuilder(source)
        nas.write_json_atomic(builder.users().model_dump(mode="json"), "users.json")
        nas.write_json_atomic(builder.units().model_dump(mode="json"), "units.json")
        project_id = source.execute(select(Project.id)).scalar_one()
        nas.write_json_atomic(builder.project(project_id).model_dump(mode="json"), "projects", f"{project_id}.json")
        nas.write_json_atomic(builder.user_public(user_id).model_dump(mode="json"), "users", user_id, "public.json")

    destination_engine = create_sqlite_engine(f"sqlite:///{(tmp_path / 'destination.db').as_posix()}")
    Base.metadata.create_all(destination_engine)
    destination_factory = create_session_factory(destination_engine)
    pull = PullService(destination_factory, nas)
    assert pull.pull_users()
    assert pull.pull_units()
    assert pull.pull_project(project_id)
    assert pull.pull_user_public(user_id)
    with destination_factory() as session:
        progress = session.get(AssignmentProgress, assignment_id)
        assert progress is not None
        assert progress.completed_quantity == 5
    destination_engine.dispose()
