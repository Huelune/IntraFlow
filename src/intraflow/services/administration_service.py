from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from intraflow.models import AppMeta, Device, Part, Project, ProjectEditor, SyncOutbox, Unit, User, WorkItem
from intraflow.services.errors import NotFoundError, PermissionDeniedError, ValidationError
from intraflow.timeutil import utc_now_iso


@dataclass(frozen=True, slots=True)
class Choice:
    id: str
    label: str


class AdministrationService:
    def __init__(self, session_factory: sessionmaker[Session], *, current_user_id: str) -> None:
        self.session_factory = session_factory
        self.current_user_id = current_user_id

    def current_permissions(self) -> tuple[bool, bool]:
        with self.session_factory() as session:
            user = self._current_user(session)
            editor = session.scalar(select(func.count()).select_from(ProjectEditor).where(
                ProjectEditor.user_id == user.id
            )) or 0
            return bool(user.is_system_admin), bool(editor)

    def list_users(self) -> list[User]:
        with self.session_factory() as session:
            return list(session.scalars(select(User).order_by(User.user_code)))

    def create_user(self, user_code: str, display_name: str, *, is_system_admin: bool = False) -> str:
        user_code, display_name = user_code.strip(), display_name.strip()
        if not user_code or not display_name:
            raise ValidationError("사용자 코드와 표시 이름은 필수입니다.")
        now, user_id = utc_now_iso(), str(uuid4())
        try:
            with self.session_factory.begin() as session:
                self._require_admin(session)
                session.add(User(id=user_id, user_code=user_code, display_name=display_name,
                                 is_system_admin=int(is_system_admin), is_active=1,
                                 created_at=now, updated_at=now, revision=1))
                self._mark_dirty(session, "USERS", "global")
        except IntegrityError as exc:
            raise ValidationError("이미 사용 중인 사용자 코드입니다.") from exc
        return user_id

    def set_user_active(self, user_id: str, active: bool) -> None:
        with self.session_factory.begin() as session:
            self._require_admin(session)
            user = session.get(User, user_id)
            if user is None:
                raise NotFoundError("사용자를 찾을 수 없습니다.")
            if user.id == self.current_user_id and not active:
                raise ValidationError("현재 사용자는 비활성화할 수 없습니다.")
            user.is_active, user.revision, user.updated_at = int(active), user.revision + 1, utc_now_iso()
            self._mark_dirty(session, "USERS", "global")

    def create_device(self, user_id: str, device_name: str) -> str:
        if not device_name.strip():
            raise ValidationError("기기 이름은 필수입니다.")
        device_id = str(uuid4())
        with self.session_factory.begin() as session:
            self._require_admin(session)
            if session.get(User, user_id) is None:
                raise NotFoundError("사용자를 찾을 수 없습니다.")
            session.add(Device(id=device_id, user_id=user_id, device_name=device_name.strip(),
                               is_current=0, created_at=utc_now_iso()))
        return device_id

    def list_units(self) -> list[Unit]:
        with self.session_factory() as session:
            return list(session.scalars(select(Unit).order_by(Unit.sort_order, Unit.code)))

    def create_unit(self, code: str, display_name: str, *, sort_order: int = 0) -> str:
        code, display_name = code.strip(), display_name.strip()
        if not code or not display_name:
            raise ValidationError("단위 코드와 표시 이름은 필수입니다.")
        unit_id = str(uuid4())
        try:
            with self.session_factory.begin() as session:
                self._require_admin(session)
                session.add(Unit(id=unit_id, code=code, display_name=display_name,
                                 is_active=1, sort_order=sort_order))
                self._increment_meta(session, "units_revision")
                self._mark_dirty(session, "UNITS", "global")
        except IntegrityError as exc:
            raise ValidationError("이미 사용 중인 단위 코드입니다.") from exc
        return unit_id

    def set_unit_active(self, unit_id: str, active: bool) -> None:
        with self.session_factory.begin() as session:
            self._require_admin(session)
            unit = session.get(Unit, unit_id)
            if unit is None:
                raise NotFoundError("단위를 찾을 수 없습니다.")
            unit.is_active = int(active)
            self._increment_meta(session, "units_revision")
            self._mark_dirty(session, "UNITS", "global")

    def list_projects(self) -> list[Project]:
        with self.session_factory() as session:
            return list(session.scalars(select(Project).where(Project.is_deleted == 0).order_by(Project.name)))

    def create_project(self, name: str, planned_start: str | None = None, planned_end: str | None = None,
                       description: str | None = None) -> str:
        self._validate_period(name, planned_start, planned_end, "프로젝트")
        project_id, now = str(uuid4()), utc_now_iso()
        with self.session_factory.begin() as session:
            self._require_admin(session)
            session.add(Project(id=project_id, name=name.strip(), description=(description or "").strip() or None,
                                planned_start=planned_start, planned_end=planned_end, status="ACTIVE", revision=1,
                                is_deleted=0, created_at=now, updated_at=now, updated_by=self.current_user_id))
            session.add(ProjectEditor(project_id=project_id, user_id=self.current_user_id))
            self._mark_dirty(session, "PROJECT", project_id)
        return project_id

    def update_project(self, project_id: str, name: str, planned_start: str | None, planned_end: str | None,
                       description: str | None = None, *, allow_child_conflicts: bool = False) -> None:
        self._validate_period(name, planned_start, planned_end, "프로젝트")
        with self.session_factory.begin() as session:
            self._require_project_manager(session, project_id)
            project = session.get(Project, project_id)
            if project is None or project.is_deleted:
                raise NotFoundError("프로젝트를 찾을 수 없습니다.")
            conflicts = list(session.scalars(select(Part).where(
                Part.project_id == project_id, Part.is_deleted == 0,
                ((Part.planned_start < planned_start) | (Part.planned_end > planned_end)))))
            if conflicts and not allow_child_conflicts:
                details = [
                    f"{project.name} > {part.name} ({part.planned_start} ~ {part.planned_end})"
                    for part in conflicts[:5]
                ]
                raise ValidationError("새 기간을 벗어나는 파트가 있습니다:\n" + "\n".join(details))
            project.name, project.description = name.strip(), (description or "").strip() or None
            project.planned_start, project.planned_end = planned_start, planned_end
            self._touch_project(session, project_id)

    def set_project_active(self, project_id: str, active: bool) -> None:
        with self.session_factory.begin() as session:
            self._require_project_manager(session, project_id)
            project = session.get(Project, project_id)
            if project is None or project.is_deleted:
                raise NotFoundError("프로젝트를 찾을 수 없습니다.")
            project.status = "ACTIVE" if active else "INACTIVE"
            self._touch_project(session, project_id)

    def add_project_editor(self, project_id: str, user_id: str) -> None:
        try:
            with self.session_factory.begin() as session:
                self._require_project_manager(session, project_id)
                user = session.get(User, user_id)
                if user is None or not user.is_active:
                    raise ValidationError("활성 사용자만 프로젝트 편집자로 지정할 수 있습니다.")
                session.add(ProjectEditor(project_id=project_id, user_id=user_id))
                self._touch_project(session, project_id)
        except IntegrityError as exc:
            raise ValidationError("이미 프로젝트 편집자로 등록된 사용자입니다.") from exc

    def list_parts(self, project_id: str | None = None) -> list[Part]:
        statement = select(Part).where(Part.is_deleted == 0)
        if project_id:
            statement = statement.where(Part.project_id == project_id)
        with self.session_factory() as session:
            return list(session.scalars(statement.order_by(Part.project_id, Part.sort_order, Part.name)))

    def create_part(self, project_id: str, name: str, weight: float, planned_start: str | None = None,
                    planned_end: str | None = None) -> str:
        self._validate_period(name, planned_start, planned_end, "파트")
        self._validate_weight(weight)
        part_id, now = str(uuid4()), utc_now_iso()
        with self.session_factory.begin() as session:
            self._require_project_manager(session, project_id)
            project = session.get(Project, project_id)
            if project is None or project.is_deleted:
                raise NotFoundError("프로젝트를 찾을 수 없습니다.")
            self._validate_within(planned_start, planned_end, project.planned_start, project.planned_end, "파트")
            session.add(Part(id=part_id, project_id=project_id, name=name.strip(), weight=weight,
                             planned_start=planned_start, planned_end=planned_end, sort_order=0,
                             is_active=1, is_deleted=0, created_at=now, updated_at=now))
            self._touch_project(session, project_id)
        return part_id

    def update_part(self, part_id: str, name: str, weight: float, planned_start: str | None,
                    planned_end: str | None, *, allow_child_conflicts: bool = False) -> None:
        self._validate_period(name, planned_start, planned_end, "파트")
        self._validate_weight(weight)
        with self.session_factory.begin() as session:
            part = session.get(Part, part_id)
            if part is None or part.is_deleted:
                raise NotFoundError("파트를 찾을 수 없습니다.")
            self._require_project_manager(session, part.project_id)
            project = session.get(Project, part.project_id)
            self._validate_within(planned_start, planned_end, project.planned_start if project else None,
                                  project.planned_end if project else None, "파트")
            conflicts = list(session.execute(
                select(WorkItem, User.display_name)
                .join(User, WorkItem.owner_user_id == User.id)
                .where(
                    WorkItem.part_id == part_id, WorkItem.is_deleted == 0,
                    ((WorkItem.planned_start < planned_start) | (WorkItem.planned_end > planned_end)),
                )
            ))
            if conflicts and not allow_child_conflicts:
                details = [
                    f"{project.name} > {part.name} > {item.name} / 소유자 {owner} "
                    f"({item.planned_start} ~ {item.planned_end})"
                    for item, owner in conflicts[:5]
                ]
                raise ValidationError("새 기간을 벗어나는 업무가 있습니다:\n" + "\n".join(details))
            part.name, part.weight, part.planned_start, part.planned_end = name.strip(), weight, planned_start, planned_end
            part.updated_at = utc_now_iso()
            self._touch_project(session, part.project_id)

    def set_part_active(self, part_id: str, active: bool) -> None:
        with self.session_factory.begin() as session:
            part = session.get(Part, part_id)
            if part is None or part.is_deleted:
                raise NotFoundError("파트를 찾을 수 없습니다.")
            self._require_project_manager(session, part.project_id)
            part.is_active, part.updated_at = int(active), utc_now_iso()
            self._touch_project(session, part.project_id)

    def choices(self) -> dict[str, list[Choice]]:
        with self.session_factory() as session:
            return {
                "users": [Choice(x.id, x.display_name) for x in session.scalars(select(User).where(User.is_active == 1).order_by(User.display_name))],
                "units": [Choice(x.id, x.display_name) for x in session.scalars(select(Unit).where(Unit.is_active == 1).order_by(Unit.sort_order, Unit.code))],
                "projects": [Choice(x.id, x.name) for x in session.scalars(select(Project).where(Project.is_deleted == 0).order_by(Project.name))],
                "parts": [Choice(x.id, x.name) for x in session.scalars(select(Part).where(Part.is_deleted == 0).order_by(Part.name))],
            }

    def _current_user(self, session: Session) -> User:
        user = session.get(User, self.current_user_id)
        if user is None or not user.is_active:
            raise PermissionDeniedError("현재 사용자가 없거나 비활성 상태입니다.")
        return user

    def _require_admin(self, session: Session) -> User:
        user = self._current_user(session)
        if not user.is_system_admin:
            raise PermissionDeniedError("시스템 관리자 권한이 필요합니다.")
        return user

    def _require_project_manager(self, session: Session, project_id: str) -> None:
        user = self._current_user(session)
        if not user.is_system_admin and session.get(ProjectEditor, (project_id, user.id)) is None:
            raise PermissionDeniedError("프로젝트 관리자 또는 편집자 권한이 필요합니다.")

    @staticmethod
    def _validate_period(name: str, start: str | None, end: str | None, label: str) -> None:
        if not name.strip():
            raise ValidationError(f"{label} 이름은 필수입니다.")
        if not start or not end:
            raise ValidationError(f"{label} 시작일과 종료일은 필수입니다.")
        if len(start) != 10 or len(end) != 10 or end < start:
            raise ValidationError("올바른 시작일과 종료일을 선택하세요.")

    @staticmethod
    def _validate_within(start: str, end: str, parent_start: str | None, parent_end: str | None, label: str) -> None:
        if (parent_start and start < parent_start) or (parent_end and end > parent_end):
            raise ValidationError(f"{label} 일정은 상위 기간 안에 있어야 합니다.")

    @staticmethod
    def _validate_weight(weight: float) -> None:
        if not 0 < weight <= 1:
            raise ValidationError("가중치는 0보다 크고 1 이하여야 합니다.")

    def _touch_project(self, session: Session, project_id: str) -> None:
        project = session.get(Project, project_id)
        if project is None:
            raise NotFoundError("프로젝트를 찾을 수 없습니다.")
        project.revision, project.updated_at, project.updated_by = project.revision + 1, utc_now_iso(), self.current_user_id
        self._mark_dirty(session, "PROJECT", project_id)

    @staticmethod
    def _increment_meta(session: Session, key: str) -> int:
        value = session.get(AppMeta, key)
        if value is None:
            value = AppMeta(key=key, value="1")
            session.add(value)
            return 1
        revision = int(value.value or "0") + 1
        value.value = str(revision)
        return revision

    @staticmethod
    def _mark_dirty(session: Session, target_type: str, target_id: str) -> None:
        target = session.scalar(select(SyncOutbox).where(
            SyncOutbox.target_type == target_type, SyncOutbox.target_id == target_id))
        if target is None:
            session.add(SyncOutbox(id=str(uuid4()), target_type=target_type, target_id=target_id,
                                   created_at=utc_now_iso(), retry_count=0))
        else:
            target.retry_count, target.next_retry_at, target.last_error = 0, None, None
