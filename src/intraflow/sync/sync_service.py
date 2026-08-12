from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from intraflow.config import settings
from intraflow.models import AppMeta, SyncOutbox, SyncState
from intraflow.services.errors import RevisionConflictError
from intraflow.sync.conflict_service import ConflictChoice, UserPublicConflict, UserPublicConflictService
from intraflow.sync.nas_client import NasClient
from intraflow.sync.pull_service import PullService
from intraflow.sync.push_service import PushService
from intraflow.sync.results import SyncOperationResult, SyncTargetResult
from intraflow.sync.shared_conflict_service import SharedConflictService
from intraflow.timeutil import utc_now_iso


@dataclass(frozen=True, slots=True)
class SyncStatus:
    pending_count: int
    last_pull_at: str | None
    last_push_at: str | None
    last_error: str | None

    @property
    def last_sync_at(self) -> str | None:
        return max(filter(None, (self.last_pull_at, self.last_push_at)), default=None)


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
        self.shared_conflict_service = SharedConflictService(
            session_factory, nas, current_user_id=current_user_id,
            conflict_root=settings.data_dir / "conflicts",
        )

    def status(self) -> SyncStatus:
        with self.session_factory() as session:
            pending = session.scalar(select(func.count()).select_from(SyncOutbox)) or 0
            pull_meta = session.get(AppMeta, "last_pull_at")
            push_meta = session.get(AppMeta, "last_push_at")
            error = session.scalar(
                select(SyncOutbox.last_error)
                .where(SyncOutbox.last_error.is_not(None))
                .order_by(SyncOutbox.created_at.desc())
                .limit(1)
            )
        return SyncStatus(
            pending_count=pending,
            last_pull_at=pull_meta.value if pull_meta else None,
            last_push_at=push_meta.value if push_meta else None,
            last_error=error,
        )

    def push_all(self) -> SyncOperationResult:
        started = utc_now_iso()
        targets = self.push_service.push_pending(current_user_id=self.current_user_id)
        result = SyncOperationResult("PUSH", started, utc_now_iso(), targets)
        if result.successful:
            self._record_operation("last_push_at", result.finished_at)
        return result

    def pull_all(self) -> SyncOperationResult:
        started = utc_now_iso()
        actions: list[tuple[str, str, object]] = []
        try:
            if self.nas.exists_json("users.json"):
                actions.append(("USERS", "global", self.pull_service.pull_users))
            if self.nas.exists_json("units.json"):
                actions.append(("UNITS", "global", self.pull_service.pull_units))
            actions.extend(("PROJECT", identity, lambda value=identity: self.pull_service.pull_project(value))
                           for identity in self.nas.list_project_ids())
            actions.extend(("USER_PUBLIC", identity,
                            lambda value=identity: self.pull_service.pull_user_public(value))
                           for identity in self.nas.list_user_ids())
        except Exception as exc:
            return SyncOperationResult("PULL", started, utc_now_iso(), (
                SyncTargetResult("NAS", "root", "FAILED", str(exc)),
            ))
        results: list[SyncTargetResult] = []
        blocked = False
        for target_type, target_id, action in actions:
            if blocked and target_type in {"PROJECT", "USER_PUBLIC"}:
                results.append(SyncTargetResult(
                    target_type, target_id, "SKIPPED", "선행 사용자 또는 단위 Pull이 실패했습니다.",
                ))
                continue
            try:
                changed = action()
            except RevisionConflictError as exc:
                results.append(SyncTargetResult(target_type, target_id, "CONFLICT", str(exc)))
                blocked = blocked or target_type in {"USERS", "UNITS"}
            except Exception as exc:
                results.append(SyncTargetResult(target_type, target_id, "FAILED", str(exc)))
                blocked = blocked or target_type in {"USERS", "UNITS"}
            else:
                results.append(SyncTargetResult(
                    target_type, target_id, "APPLIED" if changed else "UNCHANGED",
                    "로컬에 반영했습니다." if changed else "이미 최신 상태입니다.",
                ))
        result = SyncOperationResult("PULL", started, utc_now_iso(), tuple(results))
        if result.successful:
            self._record_operation("last_pull_at", result.finished_at)
        return result

    def synchronize(self) -> SyncOperationResult:
        started = utc_now_iso()
        pulled = self.pull_all()
        if not pulled.successful:
            targets = pulled.targets + (SyncTargetResult(
                "PUSH", "pending", "SKIPPED", "Pull 오류 또는 충돌이 있어 Push하지 않았습니다.",
            ),)
            return SyncOperationResult("SYNCHRONIZE", started, utc_now_iso(), targets)
        pushed = self.push_all()
        return SyncOperationResult(
            "SYNCHRONIZE", started, utc_now_iso(), pulled.targets + pushed.targets,
        )

    def _record_operation(self, key: str, value: str) -> None:
        with self.session_factory.begin() as session:
            meta = session.get(AppMeta, key)
            if meta is None:
                session.add(AppMeta(key=key, value=value))
            else:
                meta.value = value

    def inspect_user_public_conflict(self) -> UserPublicConflict:
        return self.conflict_service.inspect()

    def resolve_user_public_conflict(
        self, choices: dict[str, ConflictChoice], *, expected_remote_revision: int | None = None,
    ):
        return self.conflict_service.resolve(
            choices, expected_remote_revision=expected_remote_revision,
        )

    def inspect_shared_conflicts(self):
        return self.shared_conflict_service.inspect()

    def resolve_shared_conflicts(self, choices):
        return self.shared_conflict_service.resolve(choices)
