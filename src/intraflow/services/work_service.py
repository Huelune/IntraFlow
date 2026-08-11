from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from intraflow.models import Assignment, AssignmentProgress, Part, Project, SyncOutbox, Unit, User, WorkItem
from intraflow.services.errors import NotFoundError, PermissionDeniedError, ValidationError
from intraflow.timeutil import utc_now_iso


@dataclass(frozen=True, slots=True)
class WorkItemView:
    work_item_id: str
    assignment_id: str
    owner_user_id: str
    owner_name: str
    project_id: str
    project_name: str
    part_id: str
    part_name: str
    name: str
    description: str | None
    unit_id: str
    unit_name: str
    total_quantity: float
    weight: float
    completed_quantity: float
    planned_start: str | None
    planned_end: str | None
    schedule_start: str | None
    schedule_end: str | None
    note: str | None
    is_active: bool
    effective_active: bool
    date_warning: bool
    updated_at: str

    @property
    def progress_ratio(self) -> float:
        return self.completed_quantity / self.total_quantity if self.total_quantity else 0.0

    @property
    def path(self) -> str:
        return f"{self.project_name} / {self.part_name} / {self.name}"


class WorkService:
    def __init__(self, session_factory: sessionmaker[Session], *, current_user_id: str) -> None:
        self.session_factory = session_factory
        self.current_user_id = current_user_id

    def create_my_work_item(
        self, part_id: str, name: str, description: str | None, total_quantity: float,
        unit_id: str, weight: float, planned_start: str, planned_end: str, *, is_active: bool = True,
    ) -> str:
        self._validate_fields(name, total_quantity, weight, planned_start, planned_end)
        now, item_id, assignment_id = utc_now_iso(), str(uuid4()), str(uuid4())
        with self.session_factory.begin() as session:
            self._current_user(session)
            part, _project = self._active_parent(session, part_id)
            self._validate_within_parent(planned_start, planned_end, part.planned_start, part.planned_end)
            unit = session.get(Unit, unit_id)
            if unit is None or not unit.is_active:
                raise ValidationError("활성 단위를 선택해야 합니다.")
            session.add(WorkItem(
                id=item_id, part_id=part.id, owner_user_id=self.current_user_id,
                name=name.strip(), description=(description or "").strip() or None,
                total_quantity=total_quantity, unit_id=unit_id, weight=weight,
                planned_start=planned_start, planned_end=planned_end, sort_order=0,
                is_active=int(is_active), is_deleted=0, created_at=now, updated_at=now,
            ))
            # There is intentionally no ORM relationship between the public work
            # definition and its internal assignment. Persist the parent first so
            # SQLite can validate the assignment foreign key deterministically.
            session.flush()
            session.add(Assignment(
                id=assignment_id, work_item_id=item_id, user_id=self.current_user_id,
                allocated_quantity=total_quantity, status="ACTIVE" if is_active else "CANCELLED", is_deleted=0,
                created_at=now, updated_at=now,
            ))
            self._mark_dirty(session)
        return item_id

    def update_my_work_item(
        self, item_id: str, name: str, description: str | None, total_quantity: float,
        unit_id: str, weight: float, planned_start: str, planned_end: str, *,
        is_active: bool | None = None, part_id: str | None = None,
    ) -> None:
        self._validate_fields(name, total_quantity, weight, planned_start, planned_end)
        with self.session_factory.begin() as session:
            item, assignment = self._owned_item(session, item_id)
            target_part_id = part_id or item.part_id
            part = session.get(Part, target_part_id)
            if part is None or part.is_deleted:
                raise NotFoundError("상위 파트를 찾을 수 없습니다.")
            if target_part_id != item.part_id:
                self._active_parent(session, target_part_id)
            self._validate_within_parent(planned_start, planned_end, part.planned_start, part.planned_end)
            unit = session.get(Unit, unit_id)
            if unit is None or not unit.is_active:
                raise ValidationError("활성 단위를 선택해야 합니다.")
            progress = session.get(AssignmentProgress, assignment.id)
            completed = float(progress.completed_quantity) if progress else 0.0
            if total_quantity < completed:
                raise ValidationError("목표 수량은 현재 완료량보다 작을 수 없습니다.")
            item.name, item.description = name.strip(), (description or "").strip() or None
            item.part_id = target_part_id
            item.total_quantity, item.unit_id, item.weight = total_quantity, unit_id, weight
            item.planned_start, item.planned_end, item.updated_at = planned_start, planned_end, utc_now_iso()
            assignment.allocated_quantity, assignment.updated_at = total_quantity, item.updated_at
            if is_active is not None:
                item.is_active = int(is_active)
                assignment.status = "ACTIVE" if is_active else "CANCELLED"
            self._mark_dirty(session)

    def set_my_work_item_active(self, item_id: str, active: bool) -> None:
        with self.session_factory.begin() as session:
            item, assignment = self._owned_item(session, item_id)
            item.is_active, item.updated_at = int(active), utc_now_iso()
            assignment.status, assignment.updated_at = ("ACTIVE" if active else "CANCELLED"), item.updated_at
            self._mark_dirty(session)

    def delete_my_work_item(self, item_id: str) -> None:
        with self.session_factory.begin() as session:
            item, assignment = self._owned_item(session, item_id)
            item.is_deleted, item.is_active, item.updated_at = 1, 0, utc_now_iso()
            assignment.status, assignment.is_deleted, assignment.updated_at = "CANCELLED", 1, item.updated_at
            self._mark_dirty(session)

    def get_my_work_item(self, item_id: str) -> WorkItemView:
        rows = [row for row in self.list_my_work_items(include_inactive=True) if row.work_item_id == item_id]
        if not rows:
            raise NotFoundError("내 업무를 찾을 수 없습니다.")
        return rows[0]

    def get_team_work_item(self, item_id: str) -> WorkItemView:
        self._ensure_active_user()
        rows = [row for row in self.list_team_work_items(include_inactive=True) if row.work_item_id == item_id]
        if not rows:
            raise NotFoundError("업무를 찾을 수 없습니다.")
        return rows[0]

    def list_my_work_items(self, *, include_inactive: bool = False) -> list[WorkItemView]:
        return [row for row in self._list(include_inactive) if row.owner_user_id == self.current_user_id]

    def list_team_work_items(self, *, include_inactive: bool = False) -> list[WorkItemView]:
        return self._list(include_inactive)

    def active_projects(self) -> list[tuple[str, str]]:
        with self.session_factory() as session:
            return [(x.id, x.name) for x in session.scalars(select(Project).where(
                Project.is_deleted == 0, Project.status == "ACTIVE"
            ).order_by(Project.name))]

    def current_user_name(self) -> str:
        with self.session_factory() as session:
            return self._current_user(session).display_name

    def parts_for_project(self, project_id: str) -> list[tuple[str, str, str | None, str | None]]:
        with self.session_factory() as session:
            return [(x.id, x.name, x.planned_start, x.planned_end) for x in session.scalars(select(Part).where(
                Part.project_id == project_id, Part.is_deleted == 0, Part.is_active == 1
            ).order_by(Part.sort_order, Part.name))]

    def active_units(self) -> list[tuple[str, str]]:
        with self.session_factory() as session:
            return [(x.id, x.display_name) for x in session.scalars(select(Unit).where(
                Unit.is_active == 1
            ).order_by(Unit.sort_order, Unit.code))]

    def _list(self, include_inactive: bool) -> list[WorkItemView]:
        statement = (
            select(WorkItem, Assignment, AssignmentProgress, Part, Project, Unit, User)
            .join(Assignment, Assignment.work_item_id == WorkItem.id)
            .outerjoin(AssignmentProgress, AssignmentProgress.assignment_id == Assignment.id)
            .join(Part, WorkItem.part_id == Part.id).join(Project, Part.project_id == Project.id)
            .join(Unit, WorkItem.unit_id == Unit.id).join(User, WorkItem.owner_user_id == User.id)
            .where(WorkItem.is_deleted == 0, Assignment.is_deleted == 0)
            .order_by(Project.name, Part.sort_order, WorkItem.sort_order, WorkItem.name)
        )
        with self.session_factory() as session:
            rows = session.execute(statement).all()
        values = [WorkItemView(
            work_item_id=item.id, assignment_id=assignment.id, owner_user_id=item.owner_user_id,
            owner_name=user.display_name, project_id=project.id, project_name=project.name,
            part_id=part.id, part_name=part.name, name=item.name, description=item.description,
            unit_id=unit.id, unit_name=unit.display_name, total_quantity=float(item.total_quantity),
            weight=float(item.weight),
            completed_quantity=float(progress.completed_quantity) if progress else 0.0,
            planned_start=item.planned_start, planned_end=item.planned_end,
            schedule_start=progress.schedule_start if progress else None,
            schedule_end=progress.schedule_end if progress else None,
            note=progress.note if progress else None, is_active=bool(item.is_active),
            effective_active=bool(item.is_active and part.is_active and project.status == "ACTIVE"),
            date_warning=bool(item.planned_start < part.planned_start or item.planned_end > part.planned_end),
            updated_at=progress.updated_at if progress else item.updated_at,
        ) for item, assignment, progress, part, project, unit, user in rows]
        return values if include_inactive else [x for x in values if x.effective_active]

    def _owned_item(self, session: Session, item_id: str) -> tuple[WorkItem, Assignment]:
        self._current_user(session)
        item = session.get(WorkItem, item_id)
        if item is None or item.is_deleted:
            raise NotFoundError("업무를 찾을 수 없습니다.")
        if item.owner_user_id != self.current_user_id:
            raise PermissionDeniedError("업무 소유자만 수정하거나 삭제할 수 있습니다.")
        assignment = session.scalar(select(Assignment).where(Assignment.work_item_id == item.id))
        if assignment is None:
            raise NotFoundError("업무 진행 정보를 찾을 수 없습니다.")
        return item, assignment

    def _current_user(self, session: Session) -> User:
        user = session.get(User, self.current_user_id)
        if user is None or not user.is_active:
            raise PermissionDeniedError("현재 사용자가 없거나 비활성 상태입니다.")
        return user

    def _ensure_active_user(self) -> None:
        with self.session_factory() as session:
            self._current_user(session)

    @staticmethod
    def _active_parent(session: Session, part_id: str) -> tuple[Part, Project]:
        part = session.get(Part, part_id)
        if part is None or part.is_deleted:
            raise NotFoundError("파트를 찾을 수 없습니다.")
        project = session.get(Project, part.project_id)
        if project is None or project.is_deleted:
            raise NotFoundError("프로젝트를 찾을 수 없습니다.")
        if not part.is_active or project.status != "ACTIVE":
            raise ValidationError("활성 프로젝트와 파트에만 업무를 만들 수 있습니다.")
        return part, project

    @staticmethod
    def _validate_fields(name: str, quantity: float, weight: float, start: str, end: str) -> None:
        if not name.strip():
            raise ValidationError("업무명은 필수입니다.")
        if quantity < 0:
            raise ValidationError("목표 수량은 0 이상이어야 합니다.")
        if not 0 < weight <= 1:
            raise ValidationError("가중치는 0보다 크고 1 이하여야 합니다.")
        if not start or not end or end < start:
            raise ValidationError("올바른 시작일과 종료일을 선택하세요.")

    @staticmethod
    def _validate_within_parent(start: str, end: str, parent_start: str | None, parent_end: str | None) -> None:
        if (parent_start and start < parent_start) or (parent_end and end > parent_end):
            raise ValidationError("업무 일정은 상위 파트 기간 안에 있어야 합니다.")

    def _mark_dirty(self, session: Session) -> None:
        target = session.scalar(select(SyncOutbox).where(
            SyncOutbox.target_type == "USER_PUBLIC", SyncOutbox.target_id == self.current_user_id,
        ))
        if target is None:
            session.add(SyncOutbox(id=str(uuid4()), target_type="USER_PUBLIC", target_id=self.current_user_id,
                                   created_at=utc_now_iso(), retry_count=0))
        else:
            target.retry_count, target.next_retry_at, target.last_error = 0, None, None
