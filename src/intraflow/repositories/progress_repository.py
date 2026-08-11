from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from intraflow.models import AssignmentProgress, ProgressHistory, SyncOutbox


class ProgressRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_progress(self, assignment_id: str) -> AssignmentProgress | None:
        return self.session.get(AssignmentProgress, assignment_id)

    def add_progress(self, progress: AssignmentProgress) -> None:
        self.session.add(progress)

    def add_history(self, history: ProgressHistory) -> None:
        self.session.add(history)

    def get_outbox_target(self, target_type: str, target_id: str) -> SyncOutbox | None:
        stmt = select(SyncOutbox).where(
            SyncOutbox.target_type == target_type,
            SyncOutbox.target_id == target_id,
        )
        return self.session.scalar(stmt)

    def add_outbox(self, outbox: SyncOutbox) -> None:
        self.session.add(outbox)
