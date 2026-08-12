from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from intraflow.database import create_session_factory, create_sqlite_engine
from intraflow.models import Base
from intraflow.services.progress_service import ProgressService
from intraflow.sync.nas_client import NasClient
from intraflow.sync.pull_service import PullService
from intraflow.sync.push_service import PushService
from intraflow.sync.snapshot_builder import SnapshotBuilder
from intraflow.sync.schemas import snapshot_adapter

from workflow import build_workflow


def test_project_snapshot_contains_only_project_and_parts(session_factory: sessionmaker[Session]) -> None:
    _identity, _admin, _work, project_id, _part, _item = build_workflow(session_factory)
    with session_factory() as session:
        snapshot = SnapshotBuilder(session).project(project_id)
    assert snapshot.schema_version == 3
    assert len(snapshot.parts) == 1
    assert snapshot.work_items == []
    assert snapshot.assignments == []


def test_user_public_snapshot_contains_owned_work_and_progress(session_factory: sessionmaker[Session]) -> None:
    identity, _admin, _work, _project, _part, item = build_workflow(session_factory)
    ProgressService(session_factory, current_user_id=identity.user_id,
                    current_device_id=identity.device_id).add_delta(item.assignment_id, 4, "진행")
    with session_factory() as session:
        snapshot = SnapshotBuilder(session).user_public(identity.user_id)
    assert len(snapshot.work_items) == 1
    assert snapshot.work_items[0].owner_user_id == identity.user_id
    assert len(snapshot.assignments) == 1
    assert snapshot.progress[0].completed_quantity == 4


def test_v2_personal_schedule_is_read_but_not_written(session_factory: sessionmaker[Session]) -> None:
    identity, _admin, _work, _project, _part, item = build_workflow(session_factory)
    with session_factory() as session:
        payload = SnapshotBuilder(session).user_public(identity.user_id).model_dump(mode="json")
    payload["schema_version"] = 2
    payload["progress"] = [{
        "assignment_id": item.assignment_id,
        "user_id": identity.user_id,
        "schedule_start": "2026-08-01",
        "schedule_end": "2026-08-10",
        "completed_quantity": 0,
        "revision": 1,
        "updated_at": "2026-08-01T00:00:00Z",
        "device_id": None,
        "note": None,
    }]
    payload["team_calendar_events"] = []
    parsed = snapshot_adapter.validate_python(payload)
    output = parsed.model_dump(mode="json")
    assert "schedule_start" not in output["progress"][0]
    assert "team_calendar_events" not in output


def test_push_pull_user_owned_work_is_read_only_data(session_factory: sessionmaker[Session], tmp_path) -> None:
    identity, _admin, _work, project_id, _part, item = build_workflow(session_factory)
    ProgressService(session_factory, current_user_id=identity.user_id,
                    current_device_id=identity.device_id).add_delta(item.assignment_id, 3)
    nas = NasClient(tmp_path / "nas")
    push = PushService(session_factory, nas, current_user_id=identity.user_id)
    push.push_users()
    push.push_units()
    push.push_project(project_id)
    push.push_user_public(identity.user_id)

    engine = create_sqlite_engine(f"sqlite:///{(tmp_path / 'copy.db').as_posix()}")
    Base.metadata.create_all(engine)
    destination = create_session_factory(engine)
    pull = PullService(destination, nas)
    assert pull.pull_users()
    assert pull.pull_units()
    assert pull.pull_project(project_id)
    assert pull.pull_user_public(identity.user_id)
    with destination() as session:
        copied = SnapshotBuilder(session).user_public(identity.user_id)
    assert copied.work_items[0].name == "업무"
    assert copied.progress[0].completed_quantity == 3
    engine.dispose()
