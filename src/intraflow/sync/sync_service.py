from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from intraflow.config import settings
from intraflow.models import SyncOutbox, SyncState
from intraflow.sync.conflict_service import ConflictChoice, UserPublicConflict, UserPublicConflictService
from intraflow.sync.nas_client import NasClient
from intraflow.sync.pull_service import PullService
from intraflow.sync.push_service import PushService


@dataclass(frozen=True, slots=True)
class SyncStatus:
    pending_count: int
    last_sync_at: str | None
    last_error: str | None


class SyncService:
    def __init__(self, session_factory: sessionmaker[Session], nas: NasClient, *, current_user_id: str) -> None:
        self.session_factory = session_factory
        self.nas = nas
        self.current_user_id = current_user_id
        self.push_service = PushService(session_factory, nas, current_user_id=current_user_id)
        self.pull_service = PullService(session_factory, nas)
        self.conflict_service = UserPublicConflictService(
            session_factory, nas, user_id=current_user_id,
            conflict_root=settings.data_dir / "conflicts",
        )

    def status(self) -> SyncStatus:
        with self.session_factory() as session:
            pending = session.scalar(select(func.count()).select_from(SyncOutbox)) or 0
            latest = session.scalar(select(func.max(SyncState.last_sync_at)))
            error = session.scalar(
                select(SyncOutbox.last_error)
                .where(SyncOutbox.last_error.is_not(None))
                .order_by(SyncOutbox.created_at.desc())
                .limit(1)
            )
        return SyncStatus(pending_count=pending, last_sync_at=latest, last_error=error)

    def push_all(self) -> int:
        return self.push_service.push_pending(current_user_id=self.current_user_id)

    def pull_all(self) -> int:
        completed = 0
        if self.nas.exists_json("users.json"):
            completed += int(self.pull_service.pull_users())
        if self.nas.exists_json("units.json"):
            completed += int(self.pull_service.pull_units())
        for project_id in self.nas.list_project_ids():
            completed += int(self.pull_service.pull_project(project_id))
        for user_id in self.nas.list_user_ids():
            completed += int(self.pull_service.pull_user_public(user_id))
        return completed

    def synchronize(self) -> tuple[int, int]:
        pulled = self.pull_all()
        pushed = self.push_all()
        return pulled, pushed

    def inspect_user_public_conflict(self) -> UserPublicConflict:
        return self.conflict_service.inspect()

    def resolve_user_public_conflict(
        self, choices: dict[str, ConflictChoice], *, expected_remote_revision: int | None = None,
    ):
        return self.conflict_service.resolve(
            choices, expected_remote_revision=expected_remote_revision,
        )
