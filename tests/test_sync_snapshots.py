from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from intraflow.database import create_session_factory, create_sqlite_engine
from intraflow.models import Base
from intraflow.services.progress_service import ProgressService
from intraflow.sync.nas_client import NasClient
from intraflow.sync.pull_service import PullService
from intraflow.sync.push_service import PushService
from intraflow.sync.snapshot_builder import SnapshotBuilder

from workflow import build_workflow


def test_project_snapshot_contains_only_project_and_parts(session_factory: sessionmaker[Session]) -> None:
    _identity, _admin, _work, project_id, _part, _item = build_workflow(session_factory)
    with session_factory() as session:
        snapshot = SnapshotBuilder(session).project(project_id)
    assert snapshot.schema_version == 2
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
