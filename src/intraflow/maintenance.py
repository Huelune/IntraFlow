from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from intraflow.models import (
    Assignment, AssignmentProgress, Device, Part,
    ProgressHistory, Project, ProjectEditor, SyncOutbox, SyncState, Unit, User, WorkItem,
)


@dataclass(frozen=True, slots=True)
class ResetResult:
    preserved_users: int
    preserved_devices: int
    preserved_units: int
    deleted_rows: int


def reset_local_data(session_factory: sessionmaker[Session]) -> ResetResult:
    """Delete project-domain and personal data while preserving identities and units."""
    with session_factory.begin() as session:
        users = session.scalar(select(func.count()).select_from(User)) or 0
        devices = session.scalar(select(func.count()).select_from(Device)) or 0
        units = session.scalar(select(func.count()).select_from(Unit)) or 0
        deleted = 0
        for model in (
            ProgressHistory, AssignmentProgress, Assignment, WorkItem, Part,
            ProjectEditor, Project,
        ):
            result = session.execute(delete(model))
            deleted += result.rowcount or 0
        deleted += session.execute(delete(SyncOutbox).where(
            SyncOutbox.target_type.in_(("PROJECT", "USER_PUBLIC"))
        )).rowcount or 0
        deleted += session.execute(delete(SyncState).where(
            SyncState.source_type.in_(("PROJECT", "USER_PUBLIC"))
        )).rowcount or 0
        for model in (
            ProgressHistory, AssignmentProgress, Assignment, WorkItem, Part,
            ProjectEditor, Project,
        ):
            remaining = session.scalar(select(func.count()).select_from(model)) or 0
            if remaining:
                raise RuntimeError(f"초기화 후 {model.__tablename__} 레코드가 {remaining}개 남았습니다.")
        remaining_outbox = session.scalar(select(func.count()).select_from(SyncOutbox).where(
            SyncOutbox.target_type.in_(("PROJECT", "USER_PUBLIC")))) or 0
        remaining_state = session.scalar(select(func.count()).select_from(SyncState).where(
            SyncState.source_type.in_(("PROJECT", "USER_PUBLIC")))) or 0
        if remaining_outbox or remaining_state:
            raise RuntimeError("프로젝트/사용자 공개 동기화 상태가 완전히 초기화되지 않았습니다.")
        if (session.scalar(select(func.count()).select_from(User)) or 0) != users:
            raise RuntimeError("사용자 보존 검증에 실패했습니다.")
        if (session.scalar(select(func.count()).select_from(Device)) or 0) != devices:
            raise RuntimeError("기기 보존 검증에 실패했습니다.")
        if (session.scalar(select(func.count()).select_from(Unit)) or 0) != units:
            raise RuntimeError("단위 보존 검증에 실패했습니다.")
    return ResetResult(users, devices, units, deleted)


def list_nas_reset_targets(root: Path) -> list[Path]:
    resolved = root.resolve(strict=True)
    if resolved == Path(resolved.anchor) or len(resolved.parts) < 3:
        raise ValueError("NAS root is too broad")
    targets: list[Path] = []
    project_dir = resolved / "projects"
    user_dir = resolved / "users"
    if project_dir.is_dir():
        targets.extend(path for path in project_dir.glob("*.json") if path.is_file())
        targets.extend(path for path in project_dir.glob(".*.tmp") if path.is_file())
    if user_dir.is_dir():
        targets.extend(path for path in user_dir.glob("*/public.json") if path.is_file())
        targets.extend(path for path in user_dir.glob("*/.public.json.*.tmp") if path.is_file())
    for target in targets:
        target.resolve().relative_to(resolved)
    return sorted(set(targets))


def delete_nas_reset_targets(root: Path) -> list[Path]:
    targets = list_nas_reset_targets(root)
    for target in targets:
        target.unlink()
    return targets
