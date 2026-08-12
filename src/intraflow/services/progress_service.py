from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from intraflow.models import Assignment, AssignmentProgress, Part, ProgressHistory, Project, SyncOutbox, User, WorkItem
from intraflow.repositories import AssignmentRepository, ProgressRepository
from intraflow.services.errors import NotFoundError, PermissionDeniedError, ValidationError
from intraflow.timeutil import utc_now_iso


@dataclass(frozen=True, slots=True)
class ProgressUpdateResult:
    assignment_id: str
    previous_quantity: float
    delta_quantity: float
    current_quantity: float
    allocated_quantity: float

    @property
    def progress_ratio(self) -> float:
        if self.allocated_quantity <= 0:
            return 0.0
        return self.current_quantity / self.allocated_quantity


class ProgressService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        current_user_id: str,
        current_device_id: str | None,
    ) -> None:
        self.session_factory = session_factory
        self.current_user_id = current_user_id
        self.current_device_id = current_device_id

    def add_delta(self, assignment_id: str, delta: float, note: str | None = None) -> ProgressUpdateResult:
        if delta == 0:
            raise ValidationError("증감량은 0이 아니어야 합니다.")

        session = self.session_factory()
        try:
            with session.begin():
                assignments = AssignmentRepository(session)
                progress_repo = ProgressRepository(session)

                assignment = assignments.get(assignment_id)
                if assignment is None or assignment.is_deleted:
                    raise NotFoundError(f"assignment not found: {assignment_id}")
                if assignment.status != "ACTIVE":
                    raise ValidationError("취소되었거나 비활성인 업무는 진행량을 변경할 수 없습니다.")
                self._validate_owned_active_assignment(session, assignment)

                progress = progress_repo.get_progress(assignment_id)
                if progress is None:
                    progress = AssignmentProgress(
                        assignment_id=assignment.id,
                        user_id=self.current_user_id,
                        completed_quantity=0,
                        revision=1,
                        updated_at=utc_now_iso(),
                        device_id=self.current_device_id,
                    )
                    progress_repo.add_progress(progress)

                if progress.user_id != self.current_user_id:
                    raise PermissionDeniedError("업무와 진행 정보의 소유자가 일치하지 않습니다.")

                previous = float(progress.completed_quantity)
                current = previous + float(delta)

                if current < 0:
                    raise ValidationError("완료량은 0보다 작을 수 없습니다.")
                if current > float(assignment.allocated_quantity):
                    raise ValidationError("완료량은 목표량을 초과할 수 없습니다.")

                now = utc_now_iso()
                progress.completed_quantity = current
                progress.note = note if note is not None else progress.note
                progress.revision += 1
                progress.updated_at = now
                progress.device_id = self.current_device_id

                progress_repo.add_history(
                    ProgressHistory(
                        id=str(uuid4()),
                        assignment_id=assignment.id,
                        user_id=self.current_user_id,
                        previous_quantity=previous,
                        delta_quantity=float(delta),
                        current_quantity=current,
                        note=note,
                        created_at=now,
                        device_id=self.current_device_id,
                    )
                )

                dirty = progress_repo.get_outbox_target("USER_PUBLIC", self.current_user_id)
                if dirty is None:
                    progress_repo.add_outbox(
                        SyncOutbox(
                            id=str(uuid4()),
                            target_type="USER_PUBLIC",
                            target_id=self.current_user_id,
                            created_at=now,
                            retry_count=0,
                        )
                    )
                else:
                    # Already dirty: preserve one row per snapshot target and make it immediately retryable.
                    dirty.retry_count = 0
                    dirty.next_retry_at = None
                    dirty.last_error = None

                result = ProgressUpdateResult(
                    assignment_id=assignment.id,
                    previous_quantity=previous,
                    delta_quantity=float(delta),
                    current_quantity=current,
                    allocated_quantity=float(assignment.allocated_quantity),
                )
            return result
        finally:
            session.close()

    def set_completed_quantity(
        self, assignment_id: str, completed_quantity: float, note: str | None = None,
    ) -> ProgressUpdateResult:
        with self.session_factory() as session:
            assignment = session.get(Assignment, assignment_id)
            if assignment is None:
                raise NotFoundError("업무 진행 정보를 찾을 수 없습니다.")
            progress = session.get(AssignmentProgress, assignment_id)
            previous = float(progress.completed_quantity) if progress else 0.0
            allocated = float(assignment.allocated_quantity)
        if completed_quantity == previous:
            if note is not None:
                return self.set_note(assignment_id, note)
            return ProgressUpdateResult(assignment_id, previous, 0, previous, allocated)
        return self.add_delta(assignment_id, completed_quantity - previous, note)

    def set_note(self, assignment_id: str, note: str | None) -> ProgressUpdateResult:
        return self._update_metadata(assignment_id, note=note, update_note=True)

    def list_history(self, assignment_id: str) -> list[ProgressHistory]:
        with self.session_factory() as session:
            assignment = session.get(Assignment, assignment_id)
            if assignment is None:
                raise NotFoundError("업무 진행 정보를 찾을 수 없습니다.")
            if assignment.user_id != self.current_user_id:
                raise PermissionDeniedError("업무 소유자만 진행 이력을 조회할 수 있습니다.")
            return list(session.scalars(
                select(ProgressHistory).where(ProgressHistory.assignment_id == assignment_id)
                .order_by(ProgressHistory.created_at.desc())
            ))

    def list_public_history(self, assignment_id: str) -> list[ProgressHistory]:
        """Return shared progress history without granting mutation permission."""
        with self.session_factory() as session:
            current = session.get(User, self.current_user_id)
            if current is None or not current.is_active:
                raise PermissionDeniedError("활성 사용자만 공개 진행 이력을 조회할 수 있습니다.")
            assignment = session.get(Assignment, assignment_id)
            if assignment is None or assignment.is_deleted:
                raise NotFoundError("업무 진행 정보를 찾을 수 없습니다.")
            item = session.get(WorkItem, assignment.work_item_id)
            if item is None or item.is_deleted or item.owner_user_id != assignment.user_id:
                raise NotFoundError("공개 업무 정보를 찾을 수 없습니다.")
            return list(session.scalars(
                select(ProgressHistory).where(ProgressHistory.assignment_id == assignment_id)
                .order_by(ProgressHistory.created_at.desc())
            ))

    def _update_metadata(
        self, assignment_id: str, *, note: str | None = None, update_note: bool = False,
    ) -> ProgressUpdateResult:
        now = utc_now_iso()
        with self.session_factory.begin() as session:
            assignment = session.get(Assignment, assignment_id)
            if assignment is None or assignment.is_deleted:
                raise NotFoundError("업무 진행 정보를 찾을 수 없습니다.")
            self._validate_owned_active_assignment(session, assignment)
            progress = session.get(AssignmentProgress, assignment_id)
            if progress is None:
                progress = AssignmentProgress(
                    assignment_id=assignment_id, user_id=self.current_user_id,
                    completed_quantity=0, revision=1, updated_at=now, device_id=self.current_device_id,
                )
                session.add(progress)
            if update_note:
                progress.note = (note or "").strip() or None
                current = float(progress.completed_quantity)
                session.add(ProgressHistory(
                    id=str(uuid4()), assignment_id=assignment_id, user_id=self.current_user_id,
                    previous_quantity=current, delta_quantity=0, current_quantity=current,
                    note=progress.note, created_at=now, device_id=self.current_device_id,
                ))
            progress.revision += 1
            progress.updated_at, progress.device_id = now, self.current_device_id
            self._mark_dirty(session, now)
            current = float(progress.completed_quantity)
            return ProgressUpdateResult(
                assignment_id=assignment_id, previous_quantity=current, delta_quantity=0,
                current_quantity=current, allocated_quantity=float(assignment.allocated_quantity),
            )

    def _validate_owned_active_assignment(self, session: Session, assignment: Assignment) -> WorkItem:
        if assignment.user_id != self.current_user_id:
            raise PermissionDeniedError("업무 소유자만 진행 상태를 변경할 수 있습니다.")
        item = session.get(WorkItem, assignment.work_item_id)
        if item is None or item.is_deleted or item.owner_user_id != self.current_user_id:
            raise PermissionDeniedError("업무 소유자만 진행 상태를 변경할 수 있습니다.")
        part = session.get(Part, item.part_id)
        project = session.get(Project, part.project_id) if part else None
        if not item.is_active or part is None or not part.is_active or project is None or project.status != "ACTIVE":
            raise ValidationError("비활성 업무는 진행 상태를 변경할 수 없습니다.")
        return item

    def _mark_dirty(self, session: Session, now: str) -> None:
        dirty = session.query(SyncOutbox).filter_by(
            target_type="USER_PUBLIC", target_id=self.current_user_id,
        ).one_or_none()
        if dirty is None:
            session.add(SyncOutbox(id=str(uuid4()), target_type="USER_PUBLIC", target_id=self.current_user_id,
                                   created_at=now, retry_count=0))
        else:
            dirty.retry_count, dirty.next_retry_at, dirty.last_error = 0, None, None
