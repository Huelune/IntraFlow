from __future__ import annotations

from sqlalchemy.orm import Session

from intraflow.models import Assignment


class AssignmentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, assignment_id: str) -> Assignment | None:
        return self.session.get(Assignment, assignment_id)
