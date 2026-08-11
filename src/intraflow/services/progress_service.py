from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy.orm import Session, sessionmaker

from intraflow.models import AssignmentProgress, ProgressHistory, SyncOutbox
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
            raise ValidationError("delta must not be zero")

        session = self.session_factory()
        try:
            with session.begin():
                assignments = AssignmentRepository(session)
                progress_repo = ProgressRepository(session)

                assignment = assignments.get(assignment_id)
                if assignment is None or assignment.is_deleted:
                    raise NotFoundError(f"assignment not found: {assignment_id}")
                if assignment.status != "ACTIVE":
                    raise ValidationError("cancelled/inactive assignment cannot be updated")
                if assignment.user_id != self.current_user_id:
                    raise PermissionDeniedError("only the assignee may update progress")

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
                    raise PermissionDeniedError("progress owner mismatch")

                previous = float(progress.completed_quantity)
                current = previous + float(delta)

                if current < 0:
                    raise ValidationError("completed quantity cannot be negative")
                if current > float(assignment.allocated_quantity):
                    raise ValidationError("completed quantity cannot exceed allocated quantity")

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
