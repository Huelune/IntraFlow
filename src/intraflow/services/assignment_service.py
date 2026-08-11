from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from intraflow.models import Assignment, AssignmentProgress, Part, Project, Unit, WorkItem


@dataclass(frozen=True, slots=True)
class ActiveAssignment:
    assignment_id: str
    work_item_name: str
    project_name: str
    part_name: str
    unit_name: str
    allocated_quantity: float
    completed_quantity: float
    schedule_start: str | None
    schedule_end: str | None

    @property
    def progress_ratio(self) -> float:
        return self.completed_quantity / self.allocated_quantity if self.allocated_quantity else 0.0


class AssignmentService:
    def __init__(self, session_factory: sessionmaker[Session], *, current_user_id: str) -> None:
        self.session_factory = session_factory
        self.current_user_id = current_user_id

    def list_active(self) -> list[ActiveAssignment]:
        statement = (
            select(Assignment, WorkItem, Part, Project, Unit, AssignmentProgress)
            .join(WorkItem, Assignment.work_item_id == WorkItem.id)
            .join(Part, WorkItem.part_id == Part.id)
            .join(Project, Part.project_id == Project.id)
            .join(Unit, WorkItem.unit_id == Unit.id)
            .outerjoin(AssignmentProgress, AssignmentProgress.assignment_id == Assignment.id)
            .where(
                Assignment.user_id == self.current_user_id,
                Assignment.status == "ACTIVE",
                Assignment.is_deleted == 0,
                WorkItem.is_deleted == 0,
                Part.is_deleted == 0,
                Project.is_deleted == 0,
            )
            .order_by(Project.planned_start, Project.name, Part.sort_order, WorkItem.sort_order)
        )
        with self.session_factory() as session:
            rows = session.execute(statement).all()
        return [
            ActiveAssignment(
                assignment_id=assignment.id,
                work_item_name=work_item.name,
                project_name=project.name,
                part_name=part.name,
                unit_name=unit.display_name,
                allocated_quantity=float(assignment.allocated_quantity),
                completed_quantity=float(progress.completed_quantity) if progress else 0.0,
                schedule_start=progress.schedule_start if progress else None,
                schedule_end=progress.schedule_end if progress else None,
            )
            for assignment, work_item, part, project, unit, progress in rows
        ]

    def sync_status(self) -> str:
        from intraflow.models import SyncOutbox

        with self.session_factory() as session:
            target = session.query(SyncOutbox).filter_by(
                target_type="USER_PUBLIC", target_id=self.current_user_id
            ).one_or_none()
        if target is None:
            return "동기화됨"
        if target.last_error:
            return "동기화 실패 - 로컬 저장됨"
        return "로컬 저장됨 - 동기화 대기"
