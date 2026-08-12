from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from intraflow.config import AppSettings, RuntimeConfig
from intraflow.models import (
    Assignment, AssignmentProgress, Device, Part, ProgressHistory,
    Project, ProjectEditor, SyncOutbox, SyncState, Unit, User, WorkItem,
)
from intraflow.services.errors import SyncError, ValidationError
from intraflow.services.setup_service import SetupService
from intraflow.sync.nas_client import NasClient
from intraflow.sync.pull_service import PullService
from intraflow.sync.schemas import ProjectSnapshot, UnitsSnapshot, UserPublicSnapshot, UsersSnapshot
from intraflow.sync.snapshot_validator import SnapshotValidator
from intraflow.timeutil import utc_now_iso


@dataclass(frozen=True, slots=True)
class TeamJoinPreview:
    nas_root_path: str
    user_count: int
    unit_count: int
    project_count: int
    public_snapshot_count: int
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _JoinBundle:
    users: UsersSnapshot
    units: UnitsSnapshot | None
    projects: tuple[ProjectSnapshot, ...]
    public_snapshots: tuple[UserPublicSnapshot, ...]


class TeamJoinService:
    """Read and atomically import an existing team into an unconfigured workstation."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory
        self.validator = SnapshotValidator()

    def inspect_team(self, nas_root_path: str) -> TeamJoinPreview:
        root = self._root(nas_root_path)
        bundle = self._read_bundle(NasClient(root))
        warnings: list[str] = []
        if bundle.units is None:
            warnings.append("단위 snapshot이 없습니다. 공개 업무가 없는 팀만 합류할 수 있습니다.")
        return TeamJoinPreview(
            str(root), len(bundle.users.users),
            len(bundle.units.units) if bundle.units else 0,
            len(bundle.projects), len(bundle.public_snapshots), tuple(warnings),
        )

    def join_existing_team(
        self, nas_root_path: str, user_code: str, device_name: str,
    ) -> RuntimeConfig:
        code = user_code.strip()
        if not code:
            raise ValidationError("사용자 코드를 입력하세요.")
        root = self._root(nas_root_path)
        bundle = self._read_bundle(NasClient(root))
        matches = [user for user in bundle.users.users if user.user_code == code]
        if not matches:
            raise ValidationError(
                "등록된 사용자 코드가 아닙니다. 첫 번째 PC의 관리자가 사용자를 생성하고 Push해야 합니다."
            )
        if len(matches) != 1:
            raise ValidationError("NAS 사용자 코드가 중복되어 합류할 수 없습니다.")
        selected = matches[0]
        if not selected.is_active:
            raise ValidationError("비활성 사용자는 합류할 수 없습니다.")
        if self._is_completed_import(selected.id):
            identity = SetupService(self.session_factory).register_device_for_existing_user(
                selected.id, device_name,
            )
            return RuntimeConfig(identity.user_id, identity.device_id, str(root))
        self._assert_joinable()

        with self.session_factory.begin() as session:
            self._apply_users(session, bundle.users)
            if bundle.units is not None:
                self._apply_units(session, bundle.units)
            session.flush()
            for snapshot in bundle.projects:
                PullService._upsert_project(session, snapshot)
            session.flush()
            for snapshot in bundle.public_snapshots:
                self._apply_public(session, snapshot)
            identity = SetupService(self.session_factory).register_device_for_existing_user(
                selected.id, device_name, session=session,
            )
            self._state(session, "USERS", "global", bundle.users)
            if bundle.units is not None:
                self._state(session, "UNITS", "global", bundle.units)
            for snapshot in bundle.projects:
                self._state(session, "PROJECT", snapshot.project.id, snapshot)
            for snapshot in bundle.public_snapshots:
                self._state(session, "USER_PUBLIC", snapshot.user_id, snapshot)
        return RuntimeConfig(identity.user_id, identity.device_id, str(root))

    def _is_completed_import(self, user_id: str) -> bool:
        with self.session_factory() as session:
            return bool(
                session.get(User, user_id)
                and session.get(SyncState, ("USERS", "global"))
                and not (session.scalar(select(func.count()).select_from(SyncOutbox)) or 0)
            )

    def _assert_joinable(self) -> None:
        with self.session_factory() as session:
            domain_models = (
                Project, Part, WorkItem, Assignment, AssignmentProgress, ProgressHistory,
            )
            if any((session.scalar(select(func.count()).select_from(model)) or 0) for model in domain_models):
                raise ValidationError("로컬 업무 데이터가 있어 기존 팀 합류를 진행할 수 없습니다.")
            if session.scalar(select(func.count()).select_from(SyncOutbox)):
                raise ValidationError("전송되지 않은 로컬 변경이 있어 기존 팀 합류를 진행할 수 없습니다.")
            if session.scalar(select(func.count()).select_from(User)):
                raise ValidationError("이미 로컬 사용자가 있습니다. 안전 초기화 후 다시 합류하세요.")

    def _read_bundle(self, nas: NasClient) -> _JoinBundle:
        users = self._read(nas, "users.json")
        if not isinstance(users, UsersSnapshot):
            raise SyncError("users.json이 사용자 snapshot이 아닙니다.")
        codes = [user.user_code for user in users.users]
        if len(codes) != len(set(codes)):
            raise ValidationError("users.json에 중복 사용자 코드가 있습니다.")

        units_value = self._read(nas, "units.json", required=False)
        if units_value is not None and not isinstance(units_value, UnitsSnapshot):
            raise SyncError("units.json이 단위 snapshot이 아닙니다.")
        projects = tuple(self._read_project(nas, value) for value in nas.list_project_ids())
        public = tuple(self._read_public(nas, value) for value in nas.list_user_ids())
        snapshots = (users, *((units_value,) if units_value is not None else ()), *projects, *public)
        if any(snapshot.schema_version not in {2, 3} for snapshot in snapshots):
            raise ValidationError("기존 팀 합류는 snapshot schema v2와 v3만 지원합니다.")
        self._validate_references(users, units_value, projects, public)
        return _JoinBundle(users, units_value, projects, public)

    def _read(self, nas: NasClient, filename: str, *, required: bool = True):
        payload = nas.read_json(filename)
        if payload is None:
            if required:
                raise SyncError(f"NAS에 필수 파일이 없습니다: {filename}")
            return None
        return self.validator.validate(payload)

    def _read_project(self, nas: NasClient, project_id: str) -> ProjectSnapshot:
        payload = nas.read_json("projects", f"{project_id}.json")
        value = self.validator.validate(payload or {})
        if not isinstance(value, ProjectSnapshot) or value.project.id != project_id:
            raise SyncError(f"프로젝트 snapshot 경로와 ID가 다릅니다: {project_id}")
        return value

    def _read_public(self, nas: NasClient, user_id: str) -> UserPublicSnapshot:
        payload = nas.read_json("users", user_id, "public.json")
        value = self.validator.validate(payload or {})
        if not isinstance(value, UserPublicSnapshot) or value.user_id != user_id:
            raise SyncError(f"사용자 공개 snapshot 경로와 ID가 다릅니다: {user_id}")
        return value

    @staticmethod
    def _validate_references(
        users: UsersSnapshot, units: UnitsSnapshot | None,
        projects: tuple[ProjectSnapshot, ...], public: tuple[UserPublicSnapshot, ...],
    ) -> None:
        user_ids = {value.id for value in users.users}
        unit_ids = {value.id for value in units.units} if units else set()
        part_ids = {part.id for project in projects for part in project.parts}
        for project in projects:
            unknown_editors = set(project.editor_user_ids) - user_ids
            if unknown_editors:
                raise ValidationError(f"프로젝트 편집자 사용자가 없습니다: {sorted(unknown_editors)[0]}")
        for snapshot in public:
            if snapshot.user_id not in user_ids:
                raise ValidationError(f"공개 snapshot 사용자가 users.json에 없습니다: {snapshot.user_id}")
            work_ids = {value.id for value in snapshot.work_items}
            assignment_ids = {value.id for value in snapshot.assignments}
            for work in snapshot.work_items:
                if work.owner_user_id != snapshot.user_id or work.part_id not in part_ids:
                    raise ValidationError(f"업무 소유자 또는 파트 참조가 잘못되었습니다: {work.id}")
                if work.unit_id not in unit_ids:
                    raise ValidationError(f"업무 단위가 units.json에 없습니다: {work.id}")
            for assignment in snapshot.assignments:
                if assignment.user_id != snapshot.user_id or assignment.work_item_id not in work_ids:
                    raise ValidationError(f"업무 Assignment 참조가 잘못되었습니다: {assignment.id}")
            for progress in snapshot.progress:
                if progress.assignment_id not in assignment_ids:
                    raise ValidationError(f"진행 정보의 Assignment가 없습니다: {progress.assignment_id}")

    @staticmethod
    def _apply_users(session: Session, snapshot: UsersSnapshot) -> None:
        for data in snapshot.users:
            value = User(id=data.id)
            session.add(value)
            for field, item in data.model_dump().items():
                setattr(value, field, int(item) if field in {"is_system_admin", "is_active"} else item)

    @staticmethod
    def _apply_units(session: Session, snapshot: UnitsSnapshot) -> None:
        for data in snapshot.units:
            value = Unit(id=data.id)
            session.add(value)
            for field, item in data.model_dump().items():
                setattr(value, field, int(item) if field == "is_active" else item)

    @staticmethod
    def _apply_public(session: Session, snapshot: UserPublicSnapshot) -> None:
        for data in snapshot.work_items:
            value = WorkItem(id=data.id)
            session.add(value)
            for field, item in data.model_dump().items():
                if field != "id":
                    setattr(value, field, int(item) if field in {"is_active", "is_deleted"} else item)
        session.flush()
        for data in snapshot.assignments:
            value = Assignment(id=data.id)
            session.add(value)
            for field, item in data.model_dump().items():
                if field != "id":
                    setattr(value, field, int(item) if field == "is_deleted" else item)
        session.flush()
        for data in snapshot.progress:
            value = AssignmentProgress(assignment_id=data.assignment_id)
            session.add(value)
            for field, item in data.model_dump().items():
                setattr(value, field, None if field == "device_id" else item)
        for data in snapshot.progress_history:
            value = ProgressHistory(id=data.id)
            session.add(value)
            for field, item in data.model_dump().items():
                if field != "id":
                    setattr(value, field, None if field == "device_id" else item)

    @staticmethod
    def _state(session: Session, source_type: str, source_id: str, snapshot) -> None:
        payload = snapshot.model_dump(mode="json")
        session.add(SyncState(
            source_type=source_type, source_id=source_id, remote_revision=snapshot.revision,
            last_sync_at=utc_now_iso(),
            last_hash=sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
            base_snapshot_json=json.dumps(payload, ensure_ascii=False, sort_keys=True),
        ))

    @staticmethod
    def _root(value: str) -> Path:
        if not value.strip():
            raise ValidationError("NAS 경로를 입력하세요.")
        root = Path(value).expanduser().resolve()
        if not root.is_dir():
            raise ValidationError(f"NAS 경로에 접근할 수 없습니다: {root}")
        return root


class LocalJoinRecoveryService:
    """Back up and clear a mistaken, unused local identity before joining a team."""

    def __init__(self, session_factory: sessionmaker[Session], settings: AppSettings) -> None:
        self.session_factory = session_factory
        self.settings = settings

    def reset_for_join(self, nas_root_path: str | None) -> Path:
        with self.session_factory() as session:
            domain_models = (
                Project, Part, WorkItem, Assignment, AssignmentProgress, ProgressHistory,
            )
            if any((session.scalar(select(func.count()).select_from(model)) or 0) for model in domain_models):
                raise ValidationError("로컬 업무 또는 진행 데이터가 있어 자동 초기화할 수 없습니다.")
            disallowed = session.scalar(select(func.count()).select_from(SyncOutbox).where(
                SyncOutbox.target_type != "USERS",
            )) or 0
            if disallowed:
                raise ValidationError("사용자 외 전송 대기 변경이 있어 자동 초기화할 수 없습니다.")
            local_user_ids = set(session.scalars(select(User.id)))
        if nas_root_path and local_user_ids:
            nas = NasClient(TeamJoinService._root(nas_root_path))
            users_payload = nas.read_json("users.json")
            if users_payload:
                snapshot = SnapshotValidator().validate(users_payload)
                if isinstance(snapshot, UsersSnapshot) and local_user_ids & {item.id for item in snapshot.users}:
                    raise ValidationError("현재 로컬 사용자가 NAS 사용자 snapshot에 있어 자동 초기화할 수 없습니다.")
            if local_user_ids & set(nas.list_user_ids()):
                raise ValidationError("현재 로컬 사용자의 공개 snapshot이 NAS에 있어 자동 초기화할 수 없습니다.")

        backup_dir = self.settings.data_dir / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = backup_dir / f"before-team-join-{stamp}.db"
        with sqlite3.connect(self.settings.db_path) as source, sqlite3.connect(backup) as destination:
            source.backup(destination)

        from sqlalchemy import delete
        from intraflow.models import AppMeta

        with self.session_factory.begin() as session:
            for model in (
                ProgressHistory, AssignmentProgress, Assignment, WorkItem, Part, ProjectEditor,
                Project, Device, SyncOutbox, SyncState, Unit, User, AppMeta,
            ):
                session.execute(delete(model))
        self.settings.save_runtime_config(RuntimeConfig(None, None, nas_root_path))
        return backup
