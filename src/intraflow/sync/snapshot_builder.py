from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from intraflow.models import (
    AppMeta,
    Assignment,
    AssignmentProgress,
    Part,
    ProgressHistory,
    Project,
    ProjectEditor,
    Unit,
    User,
    WorkItem,
)
from intraflow.services.errors import NotFoundError
from intraflow.sync.schemas import (
    AssignmentData,
    AssignmentProgressData,
    PartData,
    ProgressHistoryData,
    ProjectData,
    ProjectSnapshot,
    SystemConfigSnapshot,
    UnitData,
    UnitsSnapshot,
    UserData,
    UserPublicSnapshot,
    UsersSnapshot,
    WorkItemData,
)
from intraflow.timeutil import utc_now_iso


def _revision(values: list[int]) -> int:
    return max(values, default=0)


def _user_data(value: User) -> UserData:
    return UserData(
        id=value.id,
        user_code=value.user_code,
        display_name=value.display_name,
        department=value.department,
        is_system_admin=bool(value.is_system_admin),
        is_active=bool(value.is_active),
        created_at=value.created_at,
        updated_at=value.updated_at,
        revision=value.revision,
    )


class SnapshotBuilder:
    """Builds shareable snapshots from local SQLite state without NAS access."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def system_config(self) -> SystemConfigSnapshot:
        values = {item.key: item.value or "" for item in self.session.scalars(select(AppMeta))}
        return SystemConfigSnapshot(revision=0, generated_at=utc_now_iso(), values=values)

    def users(self) -> UsersSnapshot:
        users = list(self.session.scalars(select(User).order_by(User.user_code)))
        return UsersSnapshot(
            revision=_revision([user.revision for user in users]),
            generated_at=utc_now_iso(),
            users=[_user_data(user) for user in users],
        )

    def units(self) -> UnitsSnapshot:
        units = list(self.session.scalars(select(Unit).order_by(Unit.sort_order, Unit.code)))
        revision_value = self.session.get(AppMeta, "units_revision")
        return UnitsSnapshot(
            revision=int(revision_value.value or 0) if revision_value else 0,
            generated_at=utc_now_iso(),
            units=[
                UnitData(
                    id=unit.id,
                    code=unit.code,
                    display_name=unit.display_name,
                    is_active=bool(unit.is_active),
                    sort_order=unit.sort_order,
                )
                for unit in units
            ],
        )

    def project(self, project_id: str) -> ProjectSnapshot:
        project = self.session.get(Project, project_id)
        if project is None:
            raise NotFoundError(f"project not found: {project_id}")
        parts = list(self.session.scalars(select(Part).where(Part.project_id == project.id).order_by(Part.sort_order)))
        editors = list(self.session.scalars(select(ProjectEditor.user_id).where(ProjectEditor.project_id == project.id)))
        return ProjectSnapshot(
            revision=project.revision,
            generated_at=utc_now_iso(),
            project=ProjectData(
                id=project.id,
                name=project.name,
                description=project.description,
                planned_start=project.planned_start,
                planned_end=project.planned_end,
                status=project.status,
                revision=project.revision,
                is_deleted=bool(project.is_deleted),
                created_at=project.created_at,
                updated_at=project.updated_at,
                updated_by=project.updated_by,
            ),
            editor_user_ids=editors,
            parts=[PartData(
                id=part.id, project_id=part.project_id, name=part.name, weight=part.weight,
                planned_start=part.planned_start, planned_end=part.planned_end, sort_order=part.sort_order,
                is_active=bool(part.is_active), is_deleted=bool(part.is_deleted),
                created_at=part.created_at, updated_at=part.updated_at,
            ) for part in parts],
        )

    def user_public(self, user_id: str) -> UserPublicSnapshot:
        if self.session.get(User, user_id) is None:
            raise NotFoundError(f"user not found: {user_id}")
        work_items = list(self.session.scalars(select(WorkItem).where(WorkItem.owner_user_id == user_id)))
        work_item_ids = [item.id for item in work_items]
        assignments = list(self.session.scalars(select(Assignment).where(
            Assignment.work_item_id.in_(work_item_ids)
        ))) if work_item_ids else []
        progress = list(self.session.scalars(select(AssignmentProgress).where(AssignmentProgress.user_id == user_id)))
        cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat(timespec="seconds").replace("+00:00", "Z")
        histories = list(self.session.scalars(
            select(ProgressHistory)
            .where(ProgressHistory.user_id == user_id, ProgressHistory.created_at >= cutoff)
            .order_by(ProgressHistory.created_at)
        ))
        return UserPublicSnapshot(
            revision=max(_revision([value.revision for value in progress]), len(work_items) + len(histories)),
            generated_at=utc_now_iso(),
            user_id=user_id,
            work_items=[WorkItemData(
                id=item.id, part_id=item.part_id, owner_user_id=item.owner_user_id,
                name=item.name, description=item.description, total_quantity=item.total_quantity,
                unit_id=item.unit_id, weight=item.weight, planned_start=item.planned_start,
                planned_end=item.planned_end, sort_order=item.sort_order, is_active=bool(item.is_active),
                is_deleted=bool(item.is_deleted), created_at=item.created_at, updated_at=item.updated_at,
            ) for item in work_items],
            assignments=[AssignmentData(
                id=item.id, work_item_id=item.work_item_id, user_id=item.user_id,
                allocated_quantity=item.allocated_quantity, status=item.status,
                is_deleted=bool(item.is_deleted), created_at=item.created_at, updated_at=item.updated_at,
            ) for item in assignments],
            progress=[AssignmentProgressData(
                assignment_id=item.assignment_id, user_id=item.user_id,
                completed_quantity=item.completed_quantity, note=item.note,
                revision=item.revision, updated_at=item.updated_at, device_id=item.device_id,
            ) for item in progress],
            progress_history=[ProgressHistoryData(
                id=item.id, assignment_id=item.assignment_id, user_id=item.user_id,
                previous_quantity=item.previous_quantity, delta_quantity=item.delta_quantity,
                current_quantity=item.current_quantity, note=item.note, created_at=item.created_at,
                device_id=item.device_id,
            ) for item in histories],
        )
