from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from intraflow.sync.nas_client import NasClient
from intraflow.sync.push_service import PushService
from intraflow.sync.shared_conflict_service import SharedConflictService
from intraflow.sync.sync_service import SyncService
from workflow import build_workflow


def test_push_pending_reports_revision_conflict(session_factory: sessionmaker[Session], tmp_path) -> None:
    identity, admin, _work, project_id, _part, _item = build_workflow(session_factory)
    nas = NasClient(tmp_path / "nas")
    push = PushService(session_factory, nas, current_user_id=identity.user_id)
    push.push_users()
    push.push_units()
    push.push_project(project_id)
    push.push_user_public(identity.user_id)

    admin.update_project(project_id, "로컬 변경", "2026-08-01", "2026-08-31")
    remote = nas.read_json("projects", f"{project_id}.json")
    remote["revision"] += 1
    remote["project"]["revision"] = remote["revision"]
    remote["project"]["name"] = "NAS 변경"
    nas.write_json_atomic(remote, "projects", f"{project_id}.json")

    results = push.push_pending(current_user_id=identity.user_id)
    project_result = next(value for value in results if value.target_type == "PROJECT")
    assert project_result.status == "CONFLICT"


def test_shared_conflict_service_auto_merges_different_items(
    session_factory: sessionmaker[Session], tmp_path,
) -> None:
    identity, admin, _work, project_id, part_id, _item = build_workflow(session_factory)
    nas = NasClient(tmp_path / "nas")
    push = PushService(session_factory, nas, current_user_id=identity.user_id)
    push.push_users()
    push.push_units()
    push.push_project(project_id)
    push.push_user_public(identity.user_id)

    admin.update_part(part_id, "로컬 파트", 1, "2026-08-01", "2026-08-31")
    remote = nas.read_json("projects", f"{project_id}.json")
    remote["revision"] += 1
    remote["project"]["revision"] = remote["revision"]
    remote["project"]["name"] = "NAS 프로젝트"
    nas.write_json_atomic(remote, "projects", f"{project_id}.json")

    conflicts = SharedConflictService(
        session_factory, nas, current_user_id=identity.user_id,
        conflict_root=tmp_path / "conflicts",
    )
    preview = conflicts.inspect()
    assert preview.target_count == 1
    assert preview.items == ()
    backup = conflicts.resolve({})
    assert backup.exists()
    assert admin.list_projects()[0].name == "NAS 프로젝트"
    assert admin.list_parts()[0].name == "로컬 파트"
    project_result = next(
        value for value in push.push_pending(current_user_id=identity.user_id)
        if value.target_type == "PROJECT"
    )
    assert project_result.status == "APPLIED"


def test_full_sync_pulls_then_pushes_when_remote_is_unchanged(
    session_factory: sessionmaker[Session], tmp_path,
) -> None:
    identity, admin, _work, project_id, part_id, _item = build_workflow(session_factory)
    nas = NasClient(tmp_path / "nas")
    push = PushService(session_factory, nas, current_user_id=identity.user_id)
    push.push_users()
    push.push_units()
    push.push_project(project_id)
    push.push_user_public(identity.user_id)
    admin.update_part(part_id, "동기화 파트", 1, "2026-08-01", "2026-08-31")

    result = SyncService(
        session_factory, nas, current_user_id=identity.user_id,
    ).synchronize()

    assert result.successful
    assert any(value.target_type == "PROJECT" and value.status == "APPLIED" for value in result.targets)
    assert nas.read_json("projects", f"{project_id}.json")["parts"][0]["name"] == "동기화 파트"
