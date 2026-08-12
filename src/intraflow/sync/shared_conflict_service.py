from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Literal

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from intraflow.models import Part, Project, ProjectEditor, SyncOutbox, SyncState, Unit, User
from intraflow.services.errors import PermissionDeniedError, SyncError, ValidationError
from intraflow.sync.nas_client import NasClient
from intraflow.sync.schemas import ProjectSnapshot, UnitsSnapshot, UsersSnapshot
from intraflow.sync.snapshot_builder import SnapshotBuilder
from intraflow.sync.snapshot_validator import SnapshotValidator
from intraflow.timeutil import utc_now_iso


ConflictChoice = Literal["LOCAL", "NAS"]


@dataclass(frozen=True, slots=True)
class SharedConflictItem:
    key: str
    target_type: str
    target_id: str
    label: str
    local_summary: str
    nas_summary: str


@dataclass(frozen=True, slots=True)
class SharedConflictSet:
    items: tuple[SharedConflictItem, ...]
    target_count: int


class SharedConflictService:
    """Three-way conflict resolution for shared definition snapshots."""

    def __init__(
        self, session_factory: sessionmaker[Session], nas: NasClient, *, current_user_id: str,
        conflict_root: Path,
    ) -> None:
        self.session_factory = session_factory
        self.nas = nas
        self.current_user_id = current_user_id
        self.conflict_root = conflict_root
        self.validator = SnapshotValidator()

    def inspect(self) -> SharedConflictSet:
        items: list[SharedConflictItem] = []
        target_count = 0
        for target_type, target_id in self._dirty_shared_targets():
            local, remote, base, known_revision = self._snapshots(target_type, target_id)
            if remote.revision == known_revision:
                continue
            target_count += 1
            for key, label, left, right, origin in self._entities(target_type, local, remote, base):
                if self._needs_choice(left, right, origin):
                    items.append(SharedConflictItem(
                        f"{target_type}:{target_id}:{key}", target_type, target_id, label,
                        self._summary(left), self._summary(right),
                    ))
        return SharedConflictSet(tuple(items), target_count)

    def resolve(self, choices: dict[str, ConflictChoice]) -> Path:
        preview = self.inspect()
        missing = [item.key for item in preview.items if item.key not in choices]
        if missing:
            raise ValidationError(f"충돌 선택이 필요합니다: {missing[0]}")
        backup = self._backup_root()
        for target_type, target_id in self._dirty_shared_targets():
            local, remote, base, known_revision = self._snapshots(target_type, target_id)
            if remote.revision == known_revision:
                continue
            self._write_backup(backup, target_type, target_id, local, remote, base)
            merged = self._merge(target_type, target_id, local, remote, base, choices)
            with self.session_factory.begin() as session:
                self._require_permission(session, target_type, target_id)
                self._apply(session, target_type, merged)
                self._validate_merged_invariants(session)
                state = session.get(SyncState, (target_type, target_id))
                if state is None:
                    state = SyncState(source_type=target_type, source_id=target_id)
                    session.add(state)
                state.remote_revision = remote.revision
                state.last_sync_at = utc_now_iso()
                state.base_snapshot_json = json.dumps(
                    remote.model_dump(mode="json"), ensure_ascii=False, sort_keys=True,
                )
                outbox = session.scalar(select(SyncOutbox).where(
                    SyncOutbox.target_type == target_type, SyncOutbox.target_id == target_id,
                ))
                if outbox is not None:
                    outbox.last_error = None
                    outbox.retry_count = 0
        return backup

    def _dirty_shared_targets(self) -> list[tuple[str, str]]:
        with self.session_factory() as session:
            return [(value.target_type, value.target_id) for value in session.scalars(
                select(SyncOutbox).where(SyncOutbox.target_type.in_(("USERS", "UNITS", "PROJECT")))
                .order_by(SyncOutbox.created_at)
            )]

    def _snapshots(self, target_type: str, target_id: str):
        with self.session_factory() as session:
            builder = SnapshotBuilder(session)
            local = {
                "USERS": builder.users,
                "UNITS": builder.units,
                "PROJECT": lambda: builder.project(target_id),
            }[target_type]()
            state = session.get(SyncState, (target_type, target_id))
            known_revision = state.remote_revision if state else 0
            base = (
                self.validator.validate(json.loads(state.base_snapshot_json))
                if state is not None and state.base_snapshot_json else None
            )
        path = {
            "USERS": ("users.json",),
            "UNITS": ("units.json",),
            "PROJECT": ("projects", f"{target_id}.json"),
        }[target_type]
        remote = self.validator.validate(self.nas.read_json(*path) or {})
        return local, remote, base, known_revision

    @staticmethod
    def _maps(target_type: str, snapshot) -> dict[str, object]:
        if target_type == "USERS":
            return {f"USER:{value.id}": value for value in snapshot.users}
        if target_type == "UNITS":
            return {f"UNIT:{value.id}": value for value in snapshot.units}
        values: dict[str, object] = {"PROJECT": snapshot.project}
        values.update({f"PART:{value.id}": value for value in snapshot.parts})
        values["EDITORS"] = tuple(sorted(snapshot.editor_user_ids))
        return values

    def _entities(self, target_type: str, local, remote, base):
        maps = [self._maps(target_type, value) if value is not None else {} for value in (local, remote, base)]
        for key in sorted(set().union(*(value.keys() for value in maps))):
            left, right, origin = (value.get(key) for value in maps)
            label_value = left or right or origin
            label = getattr(label_value, "display_name", None) or getattr(label_value, "name", None)
            label = label or ("프로젝트 편집자" if key == "EDITORS" else key)
            yield key, str(label), left, right, origin

    @staticmethod
    def _plain(value):
        if not hasattr(value, "model_dump"):
            return value
        data = value.model_dump(mode="json")
        for field in ("created_at", "updated_at", "updated_by", "revision"):
            data.pop(field, None)
        return data

    def _needs_choice(self, local, remote, base) -> bool:
        left, right, origin = map(self._plain, (local, remote, base))
        return left != right and left != origin and right != origin

    def _merge(self, target_type: str, target_id: str, local, remote, base, choices):
        merged = {}
        for key, _label, left, right, origin in self._entities(target_type, local, remote, base):
            plain_left, plain_right, plain_origin = map(self._plain, (left, right, origin))
            if plain_left == plain_right:
                selected = left
            elif plain_left == plain_origin:
                selected = right
            elif plain_right == plain_origin:
                selected = left
            else:
                selected = left if choices[f"{target_type}:{target_id}:{key}"] == "LOCAL" else right
            if selected is not None:
                merged[key] = selected
        update = {"revision": remote.revision}
        if target_type == "USERS":
            update["users"] = list(merged.values())
        elif target_type == "UNITS":
            update["units"] = list(merged.values())
        else:
            project = merged["PROJECT"].model_copy(update={
                "revision": remote.revision + 1,
                "updated_at": utc_now_iso(),
                "updated_by": self.current_user_id,
            })
            update.update(
                revision=remote.revision + 1,
                project=project,
                parts=[value for key, value in merged.items() if key.startswith("PART:")],
                editor_user_ids=list(merged.get("EDITORS", ())),
            )
        return remote.model_copy(update=update)

    def _require_permission(self, session: Session, target_type: str, target_id: str) -> None:
        user = session.get(User, self.current_user_id)
        if user is None or not user.is_active:
            raise PermissionDeniedError("활성 사용자만 충돌을 해결할 수 있습니다.")
        if target_type in {"USERS", "UNITS"} and not user.is_system_admin:
            raise PermissionDeniedError("시스템 관리자 권한이 필요합니다.")
        if target_type == "PROJECT" and not user.is_system_admin and session.get(
            ProjectEditor, (target_id, user.id),
        ) is None:
            raise PermissionDeniedError("프로젝트 편집자 권한이 필요합니다.")

    @staticmethod
    def _apply(session: Session, target_type: str, snapshot) -> None:
        if target_type == "USERS":
            for data in snapshot.users:
                value = session.get(User, data.id) or User(id=data.id)
                session.add(value)
                for field, item in data.model_dump().items():
                    setattr(value, field, int(item) if field in {"is_system_admin", "is_active"} else item)
            return
        if target_type == "UNITS":
            for data in snapshot.units:
                value = session.get(Unit, data.id) or Unit(id=data.id)
                session.add(value)
                for field, item in data.model_dump().items():
                    setattr(value, field, int(item) if field == "is_active" else item)
            return
        data = snapshot.project
        project = session.get(Project, data.id) or Project(id=data.id)
        session.add(project)
        for field, item in data.model_dump().items():
            if field != "id":
                setattr(project, field, int(item) if field == "is_deleted" else item)
        for data in snapshot.parts:
            part = session.get(Part, data.id) or Part(id=data.id)
            session.add(part)
            for field, item in data.model_dump().items():
                if field != "id":
                    setattr(part, field, int(item) if field in {"is_active", "is_deleted"} else item)
        session.execute(delete(ProjectEditor).where(ProjectEditor.project_id == project.id))
        for user_id in snapshot.editor_user_ids:
            session.add(ProjectEditor(project_id=project.id, user_id=user_id))

    @staticmethod
    def _summary(value) -> str:
        if value is None:
            return "없음"
        if isinstance(value, tuple):
            return f"{len(value)}명"
        name = getattr(value, "display_name", None) or getattr(value, "name", None)
        state = getattr(value, "status", None)
        if hasattr(value, "is_active"):
            state = "활성" if value.is_active else "비활성"
        return " · ".join(str(item) for item in (name, state) if item) or str(value)

    @staticmethod
    def _validate_merged_invariants(session: Session) -> None:
        active_admins = session.scalar(select(func.count()).select_from(User).where(
            User.is_system_admin == 1, User.is_active == 1,
        )) or 0
        if active_admins == 0:
            raise ValidationError("병합 결과에 활성 시스템 관리자가 없습니다.")
        active_projects = list(session.scalars(select(Project).where(
            Project.status == "ACTIVE", Project.is_deleted == 0,
        )))
        for project in active_projects:
            active_editors = session.scalar(
                select(func.count()).select_from(ProjectEditor).join(User, ProjectEditor.user_id == User.id)
                .where(ProjectEditor.project_id == project.id, User.is_active == 1)
            ) or 0
            if active_editors == 0:
                raise ValidationError(f"병합 결과에서 '{project.name}' 프로젝트의 활성 편집자가 없습니다.")

    def _backup_root(self) -> Path:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        target = self.conflict_root / stamp
        suffix = 1
        while target.exists():
            target = self.conflict_root / f"{stamp}-{suffix}"
            suffix += 1
        target.mkdir(parents=True)
        return target

    @staticmethod
    def _write_backup(root: Path, target_type: str, target_id: str, local, remote, base) -> None:
        prefix = f"{target_type.lower()}-{target_id}"
        for name, snapshot in (("local", local), ("nas", remote), ("base", base)):
            if snapshot is None:
                continue
            (root / f"{prefix}-{name}.json").write_text(
                json.dumps(snapshot.model_dump(mode="json"), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
