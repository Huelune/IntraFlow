from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from intraflow.models import (
    AppMeta,
    Assignment,
    Device,
    Part,
    ProgressHistory,
    Project,
    ProjectEditor,
    SyncOutbox,
    Unit,
    User,
    WorkItem,
)
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
            editor = session.scalar(
                select(func.count()).select_from(ProjectEditor).where(ProjectEditor.user_id == user.id)
            ) or 0
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
                session.add(User(
                    id=user_id, user_code=user_code, display_name=display_name,
                    is_system_admin=int(is_system_admin), is_active=1,
                    created_at=now, updated_at=now, revision=1,
                ))
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
            user.is_active = int(active)
            user.revision += 1
            user.updated_at = utc_now_iso()
            self._mark_dirty(session, "USERS", "global")

    def create_device(self, user_id: str, device_name: str) -> str:
        device_name = device_name.strip()
        if not device_name:
            raise ValidationError("기기 이름은 필수입니다.")
        device_id = str(uuid4())
        with self.session_factory.begin() as session:
            self._require_admin(session)
            if session.get(User, user_id) is None:
                raise NotFoundError("사용자를 찾을 수 없습니다.")
            session.add(Device(
                id=device_id, user_id=user_id, device_name=device_name,
                is_current=0, created_at=utc_now_iso(),
            ))
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
                session.add(Unit(
                    id=unit_id, code=code, display_name=display_name,
                    is_active=1, sort_order=sort_order,
                ))
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

    def create_project(self, name: str, planned_start: str | None = None, planned_end: str | None = None) -> str:
        name = name.strip()
        self._validate_name_and_period(name, planned_start, planned_end)
        project_id, now = str(uuid4()), utc_now_iso()
        with self.session_factory.begin() as session:
            self._require_admin(session)
            session.add(Project(
                id=project_id, name=name, planned_start=planned_start or None,
                planned_end=planned_end or None, status="ACTIVE", revision=1,
                is_deleted=0, created_at=now, updated_at=now, updated_by=self.current_user_id,
            ))
            session.add(ProjectEditor(project_id=project_id, user_id=self.current_user_id))
            self._mark_dirty(session, "PROJECT", project_id)
        return project_id

    def update_project(self, project_id: str, name: str, planned_start: str | None, planned_end: str | None) -> None:
        name = name.strip()
        self._validate_name_and_period(name, planned_start, planned_end)
        with self.session_factory.begin() as session:
            self._require_project_editor(session, project_id)
            project = session.get(Project, project_id)
            if project is None:
                raise NotFoundError("프로젝트를 찾을 수 없습니다.")
            project.name, project.planned_start, project.planned_end = name, planned_start or None, planned_end or None
            self._touch_project(session, project_id)

    def add_project_editor(self, project_id: str, user_id: str) -> None:
        try:
            with self.session_factory.begin() as session:
                self._require_project_editor(session, project_id)
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
            return list(session.scalars(statement.order_by(Part.project_id, Part.sort_order)))

    def create_part(self, project_id: str, name: str, weight: float, planned_start: str | None = None, planned_end: str | None = None) -> str:
        name = name.strip()
        self._validate_name_and_period(name, planned_start, planned_end)
        self._validate_weight(weight)
        part_id, now = str(uuid4()), utc_now_iso()
        with self.session_factory.begin() as session:
            self._require_project_editor(session, project_id)
            session.add(Part(
                id=part_id, project_id=project_id, name=name, weight=weight,
                planned_start=planned_start or None, planned_end=planned_end or None,
                sort_order=0, is_deleted=0, created_at=now, updated_at=now,
            ))
            self._touch_project(session, project_id)
        return part_id

    def update_part(self, part_id: str, name: str, weight: float, planned_start: str | None, planned_end: str | None) -> None:
        name = name.strip()
        self._validate_name_and_period(name, planned_start, planned_end)
        self._validate_weight(weight)
        with self.session_factory.begin() as session:
            part = session.get(Part, part_id)
            if part is None or part.is_deleted:
                raise NotFoundError("파트를 찾을 수 없습니다.")
            self._require_project_editor(session, part.project_id)
            part.name, part.weight = name, weight
            part.planned_start, part.planned_end, part.updated_at = planned_start or None, planned_end or None, utc_now_iso()
            self._touch_project(session, part.project_id)

    def list_work_items(self, part_id: str | None = None) -> list[WorkItem]:
        statement = select(WorkItem).where(WorkItem.is_deleted == 0)
        if part_id:
            statement = statement.where(WorkItem.part_id == part_id)
        with self.session_factory() as session:
            return list(session.scalars(statement.order_by(WorkItem.part_id, WorkItem.sort_order)))

    def create_work_item(self, part_id: str, name: str, total_quantity: float, unit_id: str, weight: float, planned_start: str | None = None, planned_end: str | None = None) -> str:
        name = name.strip()
        self._validate_name_and_period(name, planned_start, planned_end)
        self._validate_weight(weight)
        if total_quantity < 0:
            raise ValidationError("총 수량은 0 이상이어야 합니다.")
        item_id, now = str(uuid4()), utc_now_iso()
        with self.session_factory.begin() as session:
            part = session.get(Part, part_id)
            if part is None or part.is_deleted:
                raise NotFoundError("파트를 찾을 수 없습니다.")
            self._require_project_editor(session, part.project_id)
            unit = session.get(Unit, unit_id)
            if unit is None or not unit.is_active:
                raise ValidationError("활성 단위를 선택해야 합니다.")
            session.add(WorkItem(
                id=item_id, part_id=part_id, name=name, total_quantity=total_quantity,
                unit_id=unit_id, weight=weight, planned_start=planned_start or None,
                planned_end=planned_end or None, sort_order=0, is_deleted=0,
                created_at=now, updated_at=now,
            ))
            self._touch_project(session, part.project_id)
        return item_id

    def update_work_item(self, item_id: str, name: str, total_quantity: float, unit_id: str, weight: float, planned_start: str | None, planned_end: str | None) -> None:
        name = name.strip()
        self._validate_name_and_period(name, planned_start, planned_end)
        self._validate_weight(weight)
        if total_quantity < 0:
            raise ValidationError("총 수량은 0 이상이어야 합니다.")
        with self.session_factory.begin() as session:
            item = session.get(WorkItem, item_id)
            if item is None or item.is_deleted:
                raise NotFoundError("업무를 찾을 수 없습니다.")
            part = session.get(Part, item.part_id)
            self._require_project_editor(session, part.project_id if part else "")
            unit = session.get(Unit, unit_id)
            if unit is None or not unit.is_active:
                raise ValidationError("활성 단위를 선택해야 합니다.")
            item.name, item.total_quantity, item.unit_id, item.weight = name, total_quantity, unit_id, weight
            item.planned_start, item.planned_end, item.updated_at = planned_start or None, planned_end or None, utc_now_iso()
            self._touch_project(session, part.project_id)

    def list_assignments(self, work_item_id: str | None = None) -> list[Assignment]:
        statement = select(Assignment).where(Assignment.is_deleted == 0)
        if work_item_id:
            statement = statement.where(Assignment.work_item_id == work_item_id)
        with self.session_factory() as session:
            return list(session.scalars(statement.order_by(Assignment.created_at)))

    def create_assignment(self, work_item_id: str, user_id: str, allocated_quantity: float) -> str:
        if allocated_quantity < 0:
            raise ValidationError("배정 수량은 0 이상이어야 합니다.")
        assignment_id, now = str(uuid4()), utc_now_iso()
        try:
            with self.session_factory.begin() as session:
                item = session.get(WorkItem, work_item_id)
                if item is None or item.is_deleted:
                    raise NotFoundError("업무를 찾을 수 없습니다.")
                part = session.get(Part, item.part_id)
                self._require_project_editor(session, part.project_id if part else "")
                user = session.get(User, user_id)
                if user is None or not user.is_active:
                    raise ValidationError("활성 사용자에게만 업무를 배정할 수 있습니다.")
                session.add(Assignment(
                    id=assignment_id, work_item_id=work_item_id, user_id=user_id,
                    allocated_quantity=allocated_quantity, status="ACTIVE", is_deleted=0,
                    created_at=now, updated_at=now,
                ))
                self._touch_project(session, part.project_id)
        except IntegrityError as exc:
            raise ValidationError("해당 사용자에게 이미 배정된 업무입니다.") from exc
        return assignment_id

    def cancel_assignment(self, assignment_id: str) -> None:
        with self.session_factory.begin() as session:
            assignment = session.get(Assignment, assignment_id)
            if assignment is None:
                raise NotFoundError("배정을 찾을 수 없습니다.")
            item = session.get(WorkItem, assignment.work_item_id)
            part = session.get(Part, item.part_id) if item else None
            self._require_project_editor(session, part.project_id if part else "")
            assignment.status = "CANCELLED"
            assignment.updated_at = utc_now_iso()
            if not session.scalar(select(ProgressHistory.id).where(ProgressHistory.assignment_id == assignment.id).limit(1)):
                assignment.is_deleted = 1
            self._touch_project(session, part.project_id)

    def update_assignment_quantity(self, assignment_id: str, allocated_quantity: float) -> None:
        if allocated_quantity < 0:
            raise ValidationError("배정 수량은 0 이상이어야 합니다.")
        with self.session_factory.begin() as session:
            assignment = session.get(Assignment, assignment_id)
            if assignment is None or assignment.is_deleted:
                raise NotFoundError("배정을 찾을 수 없습니다.")
            item = session.get(WorkItem, assignment.work_item_id)
            part = session.get(Part, item.part_id) if item else None
            self._require_project_editor(session, part.project_id if part else "")
            completed = session.scalar(select(func.max(ProgressHistory.current_quantity)).where(
                ProgressHistory.assignment_id == assignment.id,
            )) or 0
            if allocated_quantity < completed:
                raise ValidationError("배정 수량은 현재 완료량보다 작을 수 없습니다.")
            assignment.allocated_quantity, assignment.updated_at = allocated_quantity, utc_now_iso()
            self._touch_project(session, part.project_id)

    def choices(self) -> dict[str, list[Choice]]:
        with self.session_factory() as session:
            return {
                "users": [Choice(x.id, x.display_name) for x in session.scalars(select(User).where(User.is_active == 1).order_by(User.display_name))],
                "units": [Choice(x.id, x.display_name) for x in session.scalars(select(Unit).where(Unit.is_active == 1).order_by(Unit.sort_order, Unit.code))],
                "projects": [Choice(x.id, x.name) for x in session.scalars(select(Project).where(Project.is_deleted == 0).order_by(Project.name))],
                "parts": [Choice(x.id, x.name) for x in session.scalars(select(Part).where(Part.is_deleted == 0).order_by(Part.name))],
                "work_items": [Choice(x.id, x.name) for x in session.scalars(select(WorkItem).where(WorkItem.is_deleted == 0).order_by(WorkItem.name))],
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

    def _require_project_editor(self, session: Session, project_id: str) -> None:
        self._current_user(session)
        if session.get(ProjectEditor, (project_id, self.current_user_id)) is None:
            raise PermissionDeniedError("프로젝트 편집자 권한이 필요합니다.")

    @staticmethod
    def _validate_name_and_period(name: str, start: str | None, end: str | None) -> None:
        if not name:
            raise ValidationError("이름은 필수입니다.")
        for value in (start, end):
            if value and (len(value) != 10 or value[4] != "-" or value[7] != "-"):
                raise ValidationError("날짜는 YYYY-MM-DD 형식이어야 합니다.")
        if start and end and end < start:
            raise ValidationError("종료일은 시작일보다 빠를 수 없습니다.")

    @staticmethod
    def _validate_weight(weight: float) -> None:
        if not 0 < weight <= 1:
            raise ValidationError("가중치는 0보다 크고 1 이하여야 합니다.")

    def _touch_project(self, session: Session, project_id: str) -> None:
        project = session.get(Project, project_id)
        if project is None:
            raise NotFoundError("프로젝트를 찾을 수 없습니다.")
        project.revision += 1
        project.updated_at = utc_now_iso()
        project.updated_by = self.current_user_id
        self._mark_dirty(session, "PROJECT", project_id)

    @staticmethod
    def _increment_meta(session: Session, key: str) -> int:
        value = session.get(AppMeta, key)
        if value is None:
            value = AppMeta(key=key, value="1")
            session.add(value)
            return 1
        revision = int(value.value or 0) + 1
        value.value = str(revision)
        return revision

    @staticmethod
    def _mark_dirty(session: Session, target_type: str, target_id: str) -> None:
        target = session.scalar(select(SyncOutbox).where(
            SyncOutbox.target_type == target_type, SyncOutbox.target_id == target_id,
        ))
        if target is None:
            session.add(SyncOutbox(
                id=str(uuid4()), target_type=target_type, target_id=target_id,
                created_at=utc_now_iso(), retry_count=0,
            ))
        else:
            target.retry_count = 0
            target.last_error = None
            target.next_retry_at = None
