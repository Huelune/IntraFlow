from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from intraflow.database import create_session_factory, create_sqlite_engine
from intraflow.config import AppSettings, RuntimeConfig
from intraflow.models import AssignmentProgress, Base, Device, SyncOutbox, SyncState, User, WorkItem
from intraflow.services.errors import SyncError, UserPublicConflictError, ValidationError
from intraflow.services.progress_service import ProgressService
from intraflow.services.setup_service import SetupService
from intraflow.sync.nas_client import NasClient
from intraflow.sync.conflict_service import UserPublicConflictService
from intraflow.sync.push_service import PushService
from intraflow.sync.team_join_service import LocalJoinRecoveryService, TeamJoinService

from workflow import build_workflow


def _published_team(session_factory: sessionmaker[Session], tmp_path):
    identity, _admin, _work, project_id, _part, item = build_workflow(session_factory)
    ProgressService(
        session_factory, current_user_id=identity.user_id,
        current_device_id=identity.device_id,
    ).add_delta(item.assignment_id, 3, "첫 PC 진행")
    nas = NasClient(tmp_path / "nas")
    push = PushService(session_factory, nas, current_user_id=identity.user_id)
    push.push_users()
    push.push_units()
    push.push_project(project_id)
    push.push_user_public(identity.user_id)
    return identity, nas


def test_existing_team_join_preserves_user_and_restores_current_public_work(
    session_factory: sessionmaker[Session], tmp_path,
) -> None:
    identity, nas = _published_team(session_factory, tmp_path)
    engine = create_sqlite_engine(f"sqlite:///{(tmp_path / 'second.db').as_posix()}")
    Base.metadata.create_all(engine)
    second = create_session_factory(engine)
    try:
        service = TeamJoinService(second)
        preview = service.inspect_team(str(nas.root_path))
        runtime = service.join_existing_team(str(nas.root_path), "owner", "SECOND-PC")

        assert preview.user_count == 1
        assert preview.project_count == 1
        assert preview.public_snapshot_count == 1
        assert runtime.current_user_id == identity.user_id
        with second() as session:
            assert session.scalar(select(func.count()).select_from(User)) == 1
            assert session.scalar(select(func.count()).select_from(Device)) == 1
            assert session.scalar(select(func.count()).select_from(WorkItem)) == 1
            assert session.scalar(select(func.count()).select_from(SyncOutbox)) == 0
            state = session.get(SyncState, ("USER_PUBLIC", identity.user_id))
            assert state is not None and state.remote_revision > 0
    finally:
        engine.dispose()


def test_join_rejects_unknown_user_without_local_changes(
    session_factory: sessionmaker[Session], tmp_path,
) -> None:
    _identity, nas = _published_team(session_factory, tmp_path)
    engine = create_sqlite_engine(f"sqlite:///{(tmp_path / 'second.db').as_posix()}")
    Base.metadata.create_all(engine)
    second = create_session_factory(engine)
    try:
        with pytest.raises(ValidationError, match="등록된 사용자 코드"):
            TeamJoinService(second).join_existing_team(str(nas.root_path), "missing", "SECOND-PC")
        with second() as session:
            assert session.scalar(select(func.count()).select_from(User)) == 0
            assert session.scalar(select(func.count()).select_from(Device)) == 0
    finally:
        engine.dispose()


def test_same_user_second_pc_cannot_overwrite_newer_public_snapshot(
    session_factory: sessionmaker[Session], tmp_path,
) -> None:
    identity, nas = _published_team(session_factory, tmp_path)
    engine = create_sqlite_engine(f"sqlite:///{(tmp_path / 'second.db').as_posix()}")
    Base.metadata.create_all(engine)
    second = create_session_factory(engine)
    try:
        runtime = TeamJoinService(second).join_existing_team(str(nas.root_path), "owner", "SECOND-PC")
        first_push = PushService(session_factory, nas, current_user_id=identity.user_id)
        with session_factory.begin() as session:
            state = session.get(SyncState, ("USER_PUBLIC", identity.user_id))
            assert state is not None
        ProgressService(
            session_factory, current_user_id=identity.user_id,
            current_device_id=identity.device_id,
        ).add_delta(next(iter(_assignment_ids(session_factory))), 1, "첫 PC 추가")
        first_push.push_user_public(identity.user_id)

        with pytest.raises(UserPublicConflictError):
            PushService(second, nas, current_user_id=runtime.current_user_id).push_user_public(
                runtime.current_user_id
            )
    finally:
        engine.dispose()


def _assignment_ids(session_factory: sessionmaker[Session]):
    from intraflow.models import Assignment

    with session_factory() as session:
        return list(session.scalars(select(Assignment.id)))


def test_same_user_conflict_can_choose_nas_and_keeps_backup(
    session_factory: sessionmaker[Session], tmp_path,
) -> None:
    identity, nas = _published_team(session_factory, tmp_path)
    engine = create_sqlite_engine(f"sqlite:///{(tmp_path / 'second.db').as_posix()}")
    Base.metadata.create_all(engine)
    second = create_session_factory(engine)
    try:
        runtime = TeamJoinService(second).join_existing_team(str(nas.root_path), "owner", "SECOND-PC")
        second_assignment = _assignment_ids(second)[0]
        ProgressService(
            second, current_user_id=runtime.current_user_id,
            current_device_id=runtime.current_device_id,
        ).add_delta(second_assignment, 2, "두 번째 PC")
        first_assignment = _assignment_ids(session_factory)[0]
        ProgressService(
            session_factory, current_user_id=identity.user_id,
            current_device_id=identity.device_id,
        ).add_delta(first_assignment, 1, "첫 번째 PC")
        PushService(session_factory, nas, current_user_id=identity.user_id).push_user_public(identity.user_id)

        conflict_service = UserPublicConflictService(
            second, nas, user_id=identity.user_id, conflict_root=tmp_path / "conflicts",
        )
        conflict = conflict_service.inspect()
        work_conflicts = [item for item in conflict.items if item.kind == "WORK"]
        assert len(work_conflicts) == 1
        remote_payload = nas.read_json("users", identity.user_id, "public.json")
        assert remote_payload is not None
        changed_payload = dict(remote_payload)
        changed_payload["revision"] = conflict.remote_revision + 1
        nas.write_json_atomic(changed_payload, "users", identity.user_id, "public.json")
        with pytest.raises(SyncError, match="다시 변경"):
            conflict_service.resolve(
                {item.key: "NAS" for item in conflict.items},
                expected_remote_revision=conflict.remote_revision,
            )
        nas.write_json_atomic(remote_payload, "users", identity.user_id, "public.json")
        backup = conflict_service.resolve(
            {item.key: "NAS" for item in conflict.items},
            expected_remote_revision=conflict.remote_revision,
        )
        assert (backup / "local.json").is_file()
        assert (backup / "nas.json").is_file()
        with second() as session:
            progress = session.get(AssignmentProgress, second_assignment)
            assert progress is not None and progress.completed_quantity == 4
            state = session.get(SyncState, ("USER_PUBLIC", identity.user_id))
            assert state is not None and state.remote_revision == conflict.remote_revision
            assert session.scalar(select(SyncOutbox).where(
                SyncOutbox.target_type == "USER_PUBLIC",
                SyncOutbox.target_id == identity.user_id,
            )) is not None
    finally:
        engine.dispose()


def test_mistaken_local_setup_is_backed_up_and_cleared(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("INTRAFLOW_CONFIG_PATH", str(tmp_path / "intraflow.local.toml"))
    settings = AppSettings()
    engine = create_sqlite_engine(settings.database_url)
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    identity = SetupService(factory).start_new_team("mistake", "Mistake", "SECOND-PC")
    settings.save_runtime_config(RuntimeConfig(
        identity.user_id, identity.device_id, None,
    ))
    try:
        backup = LocalJoinRecoveryService(factory, settings).reset_for_join(None)
        assert backup.is_file()
        with factory() as session:
            assert session.scalar(select(func.count()).select_from(User)) == 0
            assert session.scalar(select(func.count()).select_from(Device)) == 0
            assert session.scalar(select(func.count()).select_from(SyncOutbox)) == 0
        assert settings.runtime_config().current_user_id is None
    finally:
        engine.dispose()
