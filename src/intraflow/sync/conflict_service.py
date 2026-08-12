from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Literal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from intraflow.models import (
    Assignment, AssignmentProgress, CalendarEvent, ProgressHistory, SyncOutbox, SyncState, WorkItem,
)
from intraflow.services.errors import SyncError, ValidationError
from intraflow.sync.nas_client import NasClient
from intraflow.sync.schemas import UserPublicSnapshot
from intraflow.sync.snapshot_builder import SnapshotBuilder
from intraflow.sync.snapshot_validator import SnapshotValidator
from intraflow.timeutil import utc_now_iso


ConflictChoice = Literal["LOCAL", "NAS"]


@dataclass(frozen=True, slots=True)
class UserPublicConflictItem:
    key: str
    kind: Literal["WORK", "CALENDAR", "HISTORY"]
    label: str
    local_summary: str
    nas_summary: str


@dataclass(frozen=True, slots=True)
class UserPublicConflict:
    user_id: str
    known_revision: int
    remote_revision: int
    items: tuple[UserPublicConflictItem, ...]


class UserPublicConflictService:
    def __init__(
        self, session_factory: sessionmaker[Session], nas: NasClient,
        *, user_id: str, conflict_root: Path,
    ) -> None:
        self.session_factory = session_factory
        self.nas = nas
        self.user_id = user_id
        self.conflict_root = conflict_root
        self.validator = SnapshotValidator()

    def inspect(self) -> UserPublicConflict:
        local, remote, known = self._snapshots()
        return self._inspect_snapshots(local, remote, known)

    def _inspect_snapshots(
        self, local: UserPublicSnapshot, remote: UserPublicSnapshot, known: int,
    ) -> UserPublicConflict:
        items: list[UserPublicConflictItem] = []
        items.extend(self._work_differences(local, remote))
        items.extend(self._differences(
            "CALENDAR", local.team_calendar_events, remote.team_calendar_events, self._calendar_summary,
        ))
        items.extend(self._differences(
            "HISTORY", local.progress_history, remote.progress_history, self._history_summary,
        ))
        return UserPublicConflict(self.user_id, known, remote.revision, tuple(items))

    def _work_differences(self, local: UserPublicSnapshot, remote: UserPublicSnapshot):
        left_work = {value.id: value for value in local.work_items}
        right_work = {value.id: value for value in remote.work_items}
        left_assign = {value.work_item_id: value for value in local.assignments}
        right_assign = {value.work_item_id: value for value in remote.assignments}
        left_progress = {value.assignment_id: value for value in local.progress}
        right_progress = {value.assignment_id: value for value in remote.progress}
        result = []
        for work_id in sorted(set(left_work) & set(right_work)):
            left, right = left_work[work_id], right_work[work_id]
            left_assignment, right_assignment = left_assign.get(work_id), right_assign.get(work_id)
            left_current = left_progress.get(left_assignment.id) if left_assignment else None
            right_current = right_progress.get(right_assignment.id) if right_assignment else None
            values_equal = left.model_dump() == right.model_dump()
            assignments_equal = (
                left_assignment.model_dump() if left_assignment else None
            ) == (right_assignment.model_dump() if right_assignment else None)
            progress_equal = (
                left_current.model_dump(exclude={"device_id"}) if left_current else None
            ) == (right_current.model_dump(exclude={"device_id"}) if right_current else None)
            if values_equal and assignments_equal and progress_equal:
                continue
            result.append(UserPublicConflictItem(
                f"WORK:{work_id}", "WORK", left.name,
                self._work_summary(left, left_current), self._work_summary(right, right_current),
            ))
        return result

    def resolve(
        self, choices: dict[str, ConflictChoice], *, expected_remote_revision: int | None = None,
    ) -> Path:
        local, remote, _known = self._snapshots()
        if expected_remote_revision is not None and remote.revision != expected_remote_revision:
            raise SyncError("충돌 확인 후 NAS 데이터가 다시 변경되었습니다. 새로 비교하세요.")
        preview = self._inspect_snapshots(local, remote, _known)
        missing = [item.key for item in preview.items if item.key not in choices]
        if missing:
            raise ValidationError(f"충돌 선택이 필요합니다: {missing[0]}")
        backup = self._backup(local, remote)
        merged = self._merge(local, remote, choices)
        with self.session_factory.begin() as session:
            self._apply(session, merged)
            state = session.get(SyncState, ("USER_PUBLIC", self.user_id))
            if state is None:
                state = SyncState(source_type="USER_PUBLIC", source_id=self.user_id)
                session.add(state)
            state.remote_revision = remote.revision
            state.last_sync_at = utc_now_iso()
            state.last_hash = None
            outbox = session.scalar(select(SyncOutbox).where(
                SyncOutbox.target_type == "USER_PUBLIC", SyncOutbox.target_id == self.user_id,
            ))
            if outbox is None:
                session.add(SyncOutbox(
                    id=str(uuid4()), target_type="USER_PUBLIC", target_id=self.user_id,
                    created_at=utc_now_iso(), retry_count=0,
                ))
            else:
                outbox.last_error = None
        return backup

    def _snapshots(self) -> tuple[UserPublicSnapshot, UserPublicSnapshot, int]:
        with self.session_factory() as session:
            local = SnapshotBuilder(session).user_public(self.user_id)
            state = session.get(SyncState, ("USER_PUBLIC", self.user_id))
            known = state.remote_revision if state else 0
        payload = self.nas.read_json("users", self.user_id, "public.json")
        value = self.validator.validate(payload or {})
        if not isinstance(value, UserPublicSnapshot) or value.user_id != self.user_id:
            raise SyncError("현재 사용자의 NAS 공개 snapshot이 잘못되었습니다.")
        return local, value, known

    @staticmethod
    def _differences(kind, local_values, remote_values, summarizer):
        local_map = {value.id if hasattr(value, "id") else value.assignment_id: value for value in local_values}
        remote_map = {value.id if hasattr(value, "id") else value.assignment_id: value for value in remote_values}
        result = []
        for value_id in sorted(set(local_map) | set(remote_map)):
            left, right = local_map.get(value_id), remote_map.get(value_id)
            if left is None or right is None:
                continue
            if left is not None and right is not None and left.model_dump() == right.model_dump():
                continue
            label_value = left or right
            result.append(UserPublicConflictItem(
                f"{kind}:{value_id}", kind, getattr(label_value, "name", None)
                or getattr(label_value, "title", None) or value_id,
                summarizer(left) if left else "없음", summarizer(right) if right else "없음",
            ))
        return result

    def _merge(self, local, remote, choices) -> UserPublicSnapshot:
        work = self._choose("WORK", local.work_items, remote.work_items, choices)
        work_source = {
            value.id: choices.get(f"WORK:{value.id}", "LOCAL") for value in work
        }
        local_assign = {value.work_item_id: value for value in local.assignments}
        remote_assign = {value.work_item_id: value for value in remote.assignments}
        assignments = []
        for value in work:
            source = local_assign if work_source[value.id] == "LOCAL" else remote_assign
            fallback = remote_assign if source is local_assign else local_assign
            assignment = source.get(value.id) or fallback.get(value.id)
            if assignment is not None:
                assignments.append(assignment)
        selected_assignment_ids = {value.id for value in assignments}
        local_progress = {value.assignment_id: value for value in local.progress}
        remote_progress = {value.assignment_id: value for value in remote.progress}
        progress = []
        for assignment in assignments:
            source = local_progress if work_source[assignment.work_item_id] == "LOCAL" else remote_progress
            fallback = remote_progress if source is local_progress else local_progress
            value = source.get(assignment.id) or fallback.get(assignment.id)
            if value is not None:
                progress.append(value)
        history = self._choose("HISTORY", local.progress_history, remote.progress_history, choices)
        history = [value for value in history if value.assignment_id in selected_assignment_ids]
        calendar = self._choose("CALENDAR", local.team_calendar_events, remote.team_calendar_events, choices)
        return UserPublicSnapshot(
            revision=remote.revision, generated_at=utc_now_iso(), user_id=self.user_id,
            work_items=work, assignments=assignments, progress=progress,
            progress_history=history, team_calendar_events=calendar,
        )

    @staticmethod
    def _choose(kind, local_values, remote_values, choices):
        id_of = lambda value: value.id if hasattr(value, "id") else value.assignment_id
        left = {id_of(value): value for value in local_values}
        right = {id_of(value): value for value in remote_values}
        merged = []
        for value_id in sorted(set(left) | set(right)):
            local_value, remote_value = left.get(value_id), right.get(value_id)
            if local_value is None or remote_value is None:
                merged.append(local_value or remote_value)
                continue
            if local_value is not None and remote_value is not None and local_value.model_dump() == remote_value.model_dump():
                merged.append(local_value)
                continue
            choice = choices[f"{kind}:{value_id}"]
            selected = local_value if choice == "LOCAL" else remote_value
            if selected is not None:
                merged.append(selected)
        return merged

    def _apply(self, session: Session, snapshot: UserPublicSnapshot) -> None:
        for data in snapshot.work_items:
            value = session.get(WorkItem, data.id) or WorkItem(id=data.id)
            session.add(value)
            for field, item in data.model_dump().items():
                if field != "id":
                    setattr(value, field, int(item) if field in {"is_active", "is_deleted"} else item)
        session.flush()
        for data in snapshot.assignments:
            value = session.get(Assignment, data.id) or Assignment(id=data.id)
            session.add(value)
            for field, item in data.model_dump().items():
                if field != "id":
                    setattr(value, field, int(item) if field == "is_deleted" else item)
        session.flush()
        for data in snapshot.progress:
            value = session.get(AssignmentProgress, data.assignment_id) or AssignmentProgress(
                assignment_id=data.assignment_id,
            )
            session.add(value)
            for field, item in data.model_dump().items():
                setattr(value, field, None if field == "device_id" else item)
        for data in snapshot.progress_history:
            value = session.get(ProgressHistory, data.id) or ProgressHistory(id=data.id)
            session.add(value)
            for field, item in data.model_dump().items():
                if field != "id":
                    setattr(value, field, None if field == "device_id" else item)
        for data in snapshot.team_calendar_events:
            value = session.get(CalendarEvent, data.id) or CalendarEvent(id=data.id)
            session.add(value)
            for field, item in data.model_dump().items():
                if field != "id":
                    setattr(value, field, int(item) if field == "is_deleted" else item)

    def _backup(self, local: UserPublicSnapshot, remote: UserPublicSnapshot) -> Path:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        target = self.conflict_root / stamp
        suffix = 1
        while target.exists():
            target = self.conflict_root / f"{stamp}-{suffix}"
            suffix += 1
        target.mkdir(parents=True)
        for name, snapshot in (("local.json", local), ("nas.json", remote)):
            (target / name).write_text(
                json.dumps(snapshot.model_dump(mode="json"), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        return target

    @staticmethod
    def _work_summary(value, progress=None) -> str:
        current = progress.completed_quantity if progress else 0
        note = progress.note if progress and progress.note else ""
        return (
            f"{value.name} | {value.planned_start}~{value.planned_end} | "
            f"{current}/{value.total_quantity} | {note}"
        )

    @staticmethod
    def _calendar_summary(value) -> str:
        return f"{value.title} | {value.start_at}~{value.end_at or ''}"

    @staticmethod
    def _history_summary(value) -> str:
        return f"{value.created_at} | {value.previous_quantity}→{value.current_quantity} | {value.note or ''}"
