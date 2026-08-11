from __future__ import annotations

from hashlib import sha256

from sqlalchemy.orm import Session, sessionmaker

from intraflow.models import ProjectEditor, SyncOutbox, SyncState, User
from intraflow.services.errors import PermissionDeniedError, RevisionConflictError, SyncError
from intraflow.sync.lock_manager import LockManager
from intraflow.sync.nas_client import NasClient
from intraflow.sync.snapshot_builder import SnapshotBuilder
from intraflow.timeutil import utc_now_iso


def _snapshot_hash(payload: dict[str, object]) -> str:
    import json

    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


class PushService:
    def __init__(self, session_factory: sessionmaker[Session], nas: NasClient) -> None:
        self.session_factory = session_factory
        self.nas = nas
        self.locks = LockManager(nas.root_path)

    def push_user_public(self, user_id: str) -> int:
        with self.session_factory() as session:
            snapshot = SnapshotBuilder(session).user_public(user_id)
        remote = self.nas.read_json("users", user_id, "public.json")
        remote_revision = int(remote.get("revision", 0)) if remote else 0
        outbound = snapshot.model_copy(update={"revision": max(snapshot.revision, remote_revision + 1)})
        payload = outbound.model_dump(mode="json")
        self.nas.write_json_atomic(payload, "users", user_id, "public.json")
        self._record_success("USER_PUBLIC", user_id, outbound.revision, payload, clear_outbox=True)
        return outbound.revision

    def push_project(self, project_id: str) -> int:
        with self.session_factory() as session:
            snapshot = SnapshotBuilder(session).project(project_id)
            state = session.get(SyncState, ("PROJECT", project_id))
            known_remote_revision = state.remote_revision if state is not None else 0
        with self.locks.acquire(f"project-{project_id}"):
            remote = self.nas.read_json("projects", f"{project_id}.json")
            remote_revision = int(remote.get("revision", 0)) if remote else 0
            if remote_revision != known_remote_revision:
                raise RevisionConflictError(
                    "project has changed on NAS; pull the latest snapshot before applying changes again"
                )
            if snapshot.revision <= remote_revision:
                raise RevisionConflictError("project revision is not newer than the NAS revision")
            payload = snapshot.model_dump(mode="json")
            self.nas.write_json_atomic(payload, "projects", f"{project_id}.json")
        self._record_success("PROJECT", project_id, snapshot.revision, payload, clear_outbox=True)
        return snapshot.revision

    def push_users(self) -> int:
        with self.session_factory() as session:
            snapshot = SnapshotBuilder(session).users()
        return self._push_global("USERS", snapshot, "users.json")

    def push_units(self) -> int:
        with self.session_factory() as session:
            snapshot = SnapshotBuilder(session).units()
        return self._push_global("UNITS", snapshot, "units.json")

    def push_pending(self, *, current_user_id: str) -> int:
        with self.session_factory() as session:
            targets = list(session.scalars(session.query(SyncOutbox).order_by(SyncOutbox.created_at).statement))
            user = session.get(User, current_user_id)
            is_admin = bool(user and user.is_system_admin)
            editable_projects = set(session.scalars(
                session.query(ProjectEditor.project_id).filter_by(user_id=current_user_id).statement
            ))
        completed = 0
        for target in targets:
            try:
                if target.target_type == "USER_PUBLIC" and target.target_id == current_user_id:
                    self.push_user_public(target.target_id)
                elif target.target_type == "USERS" and is_admin:
                    self.push_users()
                elif target.target_type == "UNITS" and is_admin:
                    self.push_units()
                elif target.target_type == "PROJECT" and target.target_id in editable_projects:
                    self.push_project(target.target_id)
                else:
                    raise PermissionDeniedError("해당 동기화 대상을 업로드할 권한이 없습니다.")
                completed += 1
            except SyncError as exc:
                self._record_failure(target.id, str(exc))
        return completed

    def _push_global(self, source_type: str, snapshot, filename: str) -> int:
        with self.session_factory() as session:
            state = session.get(SyncState, (source_type, "global"))
            known_revision = state.remote_revision if state else 0
        with self.locks.acquire(source_type.lower()):
            remote = self.nas.read_json(filename)
            remote_revision = int(remote.get("revision", 0)) if remote else 0
            if remote_revision != known_revision:
                raise RevisionConflictError("NAS 데이터가 변경되었습니다. 먼저 Pull을 실행하세요.")
            outbound = snapshot.model_copy(update={"revision": max(snapshot.revision, remote_revision + 1)})
            payload = outbound.model_dump(mode="json")
            self.nas.write_json_atomic(payload, filename)
        self._record_success(source_type, "global", outbound.revision, payload, clear_outbox=True)
        return outbound.revision

    def _record_success(
        self,
        source_type: str,
        source_id: str,
        revision: int,
        payload: dict[str, object],
        *,
        clear_outbox: bool,
    ) -> None:
        with self.session_factory.begin() as session:
            state = session.get(SyncState, (source_type, source_id))
            if state is None:
                state = SyncState(source_type=source_type, source_id=source_id)
                session.add(state)
            state.remote_revision = revision
            state.last_sync_at = utc_now_iso()
            state.last_hash = _snapshot_hash(payload)
            if clear_outbox:
                outbox = session.query(SyncOutbox).filter_by(target_type=source_type, target_id=source_id).one_or_none()
                if outbox is not None:
                    session.delete(outbox)

    def _record_failure(self, outbox_id: str, message: str) -> None:
        with self.session_factory.begin() as session:
            target = session.get(SyncOutbox, outbox_id)
            if target is not None:
                target.retry_count += 1
                target.last_error = message
                target.next_retry_at = None
