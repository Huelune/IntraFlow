from __future__ import annotations

from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from intraflow.maintenance import delete_nas_reset_targets, list_nas_reset_targets, reset_local_data
from intraflow.models import Assignment, Device, Part, Project, Unit, User, WorkItem

from workflow import build_workflow


def test_local_reset_preserves_users_devices_and_units(session_factory: sessionmaker[Session]) -> None:
    build_workflow(session_factory)
    result = reset_local_data(session_factory)
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(User)) == result.preserved_users
        assert session.scalar(select(func.count()).select_from(Device)) == result.preserved_devices
        assert session.scalar(select(func.count()).select_from(Unit)) == result.preserved_units
        for model in (Assignment, WorkItem, Part, Project):
            assert session.scalar(select(func.count()).select_from(model)) == 0


def test_nas_reset_deletes_only_project_and_public_snapshots(tmp_path: Path) -> None:
    root = tmp_path / "nas-root"
    (root / "projects").mkdir(parents=True)
    (root / "users" / "user-id").mkdir(parents=True)
    (root / "projects" / "project.json").write_text("{}", encoding="utf-8")
    (root / "users" / "user-id" / "public.json").write_text("{}", encoding="utf-8")
    (root / "users.json").write_text("{}", encoding="utf-8")
    (root / "units.json").write_text("{}", encoding="utf-8")
    targets = list_nas_reset_targets(root)
    assert len(targets) == 2
    delete_nas_reset_targets(root)
    assert (root / "users.json").exists()
    assert (root / "units.json").exists()
    assert not (root / "projects" / "project.json").exists()
