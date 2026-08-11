from __future__ import annotations

from hashlib import sha256
import json

from sqlalchemy.orm import Session, sessionmaker

from intraflow.models import (
    Assignment,
    AssignmentProgress,
    CalendarEvent,
    Part,
    ProgressHistory,
    Project,
    ProjectEditor,
    SyncOutbox,
    SyncState,
    Unit,
    User,
    WorkItem,
)
from intraflow.services.errors import SyncError
from intraflow.sync.nas_client import NasClient
from intraflow.sync.schemas import (
    ProjectSnapshot,
    Snapshot,
    UnitsSnapshot,
    UserPublicSnapshot,
    UsersSnapshot,
)
from intraflow.sync.snapshot_validator import SnapshotValidator
from intraflow.timeutil import utc_now_iso


def _hash(payload: dict[str, object]) -> str:
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


class PullService:
    def __init__(self, session_factory: sessionmaker[Session], nas: NasClient) -> None:
        self.session_factory = session_factory
        self.nas = nas
        self.validator = SnapshotValidator()

    def pull_users(self) -> bool:
        snapshot = self._read("USERS", "global", "users.json")
        if not isinstance(snapshot, UsersSnapshot):
            raise SyncError("users.json is not a USERS snapshot")
        with self.session_factory.begin() as session:
            if session.query(SyncOutbox).filter_by(target_type="USERS", target_id="global").one_or_none():
                raise SyncError("로컬 사용자 변경이 있어 Pull할 수 없습니다. 먼저 Push하거나 충돌을 해결하세요.")
            if not self._newer(session, "USERS", "global", snapshot.revision):
                return False
            for data in snapshot.users:
                value = session.get(User, data.id)
                if value is None:
                    value = User(id=data.id)
                    session.add(value)
                for field, item in data.model_dump().items():
                    setattr(value, field, int(item) if field in {"is_system_admin", "is_active"} else item)
            self._state(session, "USERS", "global", snapshot.revision, snapshot.model_dump(mode="json"))
        return True

    def pull_units(self) -> bool:
        snapshot = self._read("UNITS", "global", "units.json")
        if not isinstance(snapshot, UnitsSnapshot):
            raise SyncError("units.json is not a UNITS snapshot")
        with self.session_factory.begin() as session:
            if session.query(SyncOutbox).filter_by(target_type="UNITS", target_id="global").one_or_none():
                raise SyncError("로컬 단위 변경이 있어 Pull할 수 없습니다. 먼저 Push하거나 충돌을 해결하세요.")
            if not self._newer(session, "UNITS", "global", snapshot.revision):
                return False
            for data in snapshot.units:
                value = session.get(Unit, data.id)
                if value is None:
                    value = Unit(id=data.id)
                    session.add(value)
                for field, item in data.model_dump().items():
                    setattr(value, field, int(item) if field == "is_active" else item)
            self._state(session, "UNITS", "global", snapshot.revision, snapshot.model_dump(mode="json"))
        return True

    def pull_project(self, project_id: str) -> bool:
        snapshot = self._read("PROJECT", project_id, "projects", f"{project_id}.json")
        if not isinstance(snapshot, ProjectSnapshot) or snapshot.project.id != project_id:
            raise SyncError("project path does not match project snapshot")
        with self.session_factory.begin() as session:
            dirty = session.query(SyncOutbox).filter_by(target_type="PROJECT", target_id=project_id).one_or_none()
            if dirty is not None:
                raise SyncError("로컬 프로젝트 변경이 있어 Pull할 수 없습니다. 먼저 Push하거나 충돌을 해결하세요.")
            if not self._newer(session, "PROJECT", project_id, snapshot.revision):
                return False
            self._upsert_project(session, snapshot)
            self._state(session, "PROJECT", project_id, snapshot.revision, snapshot.model_dump(mode="json"))
        return True

    def pull_user_public(self, user_id: str) -> bool:
        snapshot = self._read("USER_PUBLIC", user_id, "users", user_id, "public.json")
        if not isinstance(snapshot, UserPublicSnapshot) or snapshot.user_id != user_id:
            raise SyncError("user public path does not match user snapshot")
        with self.session_factory.begin() as session:
            if not self._newer(session, "USER_PUBLIC", user_id, snapshot.revision):
                return False
            if session.get(User, user_id) is None:
                raise SyncError("pull users before user public progress")
            for data in snapshot.progress:
                if session.get(Assignment, data.assignment_id) is None:
                    raise SyncError("pull project definitions before user public progress")
                value = session.get(AssignmentProgress, data.assignment_id)
                if value is None:
                    value = AssignmentProgress(assignment_id=data.assignment_id)
                    session.add(value)
                values = data.model_dump()
                # Devices are local-only records and cannot be referenced on another user's PC.
                values["device_id"] = None
                for field, item in values.items():
                    setattr(value, field, item)
            for data in snapshot.progress_history:
                value = session.get(ProgressHistory, data.id)
                if value is None:
                    value = ProgressHistory(id=data.id)
                    session.add(value)
                    values = data.model_dump()
                    values["device_id"] = None
                    for field, item in values.items():
                        if field != "id":
                            setattr(value, field, item)
            for data in snapshot.team_calendar_events:
                value = session.get(CalendarEvent, data.id)
                if value is None:
                    value = CalendarEvent(id=data.id)
                    session.add(value)
                for field, item in data.model_dump().items():
                    if field != "id":
                        setattr(value, field, int(item) if field == "is_deleted" else item)
            self._state(session, "USER_PUBLIC", user_id, snapshot.revision, snapshot.model_dump(mode="json"))
        return True

    def _read(self, source_type: str, source_id: str, *path: str) -> Snapshot:
        payload = self.nas.read_json(*path)
        if payload is None:
            raise SyncError(f"NAS snapshot missing for {source_type}:{source_id}")
        return self.validator.validate(payload)

    @staticmethod
    def _newer(session: Session, source_type: str, source_id: str, revision: int) -> bool:
        state = session.get(SyncState, (source_type, source_id))
        return state is None or revision > state.remote_revision

    @staticmethod
    def _state(session: Session, source_type: str, source_id: str, revision: int, payload: dict[str, object]) -> None:
        state = session.get(SyncState, (source_type, source_id))
        if state is None:
            state = SyncState(source_type=source_type, source_id=source_id)
            session.add(state)
        state.remote_revision = revision
        state.last_sync_at = utc_now_iso()
        state.last_hash = _hash(payload)

    @staticmethod
    def _upsert_project(session: Session, snapshot: ProjectSnapshot) -> None:
        data = snapshot.project
        project = session.get(Project, data.id)
        if project is None:
            project = Project(id=data.id)
            session.add(project)
        project_values = data.model_dump()
        for field, item in project_values.items():
            if field != "id":
                if field == "updated_by" and item is not None and session.get(User, item) is None:
                    item = None
                setattr(project, field, int(item) if field == "is_deleted" else item)
        for data in snapshot.parts:
            value = session.get(Part, data.id)
            if value is None:
                value = Part(id=data.id)
                session.add(value)
            for field, item in data.model_dump().items():
                if field != "id":
                    setattr(value, field, int(item) if field == "is_deleted" else item)
        for data in snapshot.work_items:
            if session.get(Unit, data.unit_id) is None:
                raise SyncError("pull units before project definitions")
            value = session.get(WorkItem, data.id)
            if value is None:
                value = WorkItem(id=data.id)
                session.add(value)
            for field, item in data.model_dump().items():
                if field != "id":
                    setattr(value, field, int(item) if field == "is_deleted" else item)
        for data in snapshot.assignments:
            if session.get(User, data.user_id) is None:
                raise SyncError("pull users before project assignments")
            value = session.get(Assignment, data.id)
            if value is None:
                value = Assignment(id=data.id)
                session.add(value)
            for field, item in data.model_dump().items():
                if field != "id":
                    setattr(value, field, int(item) if field == "is_deleted" else item)
        existing = {item.user_id: item for item in session.query(ProjectEditor).filter_by(project_id=project.id)}
        desired = set(snapshot.editor_user_ids)
        for user_id, value in existing.items():
            if user_id not in desired:
                session.delete(value)
        for user_id in desired - set(existing):
            if session.get(User, user_id) is not None:
                session.add(ProjectEditor(project_id=project.id, user_id=user_id))
