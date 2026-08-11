from __future__ import annotations

from typing import Optional

from sqlalchemy import CheckConstraint, ForeignKey, Index, PrimaryKeyConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from intraflow.models.base import Base

BOOL_CHECK = "{} IN (0, 1)"


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(BOOL_CHECK.format("is_system_admin"), name="users_system_admin_bool"),
        CheckConstraint(BOOL_CHECK.format("is_active"), name="users_active_bool"),
        Index("idx_users_active", "is_active"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_code: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    department: Mapped[Optional[str]] = mapped_column(String)
    is_system_admin: Mapped[int] = mapped_column(default=0, nullable=False)
    is_active: Mapped[int] = mapped_column(default=1, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)
    revision: Mapped[int] = mapped_column(default=1, nullable=False)


class Device(Base):
    __tablename__ = "devices"
    __table_args__ = (
        CheckConstraint(BOOL_CHECK.format("is_current"), name="devices_current_bool"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    device_name: Mapped[Optional[str]] = mapped_column(String)
    is_current: Mapped[int] = mapped_column(default=0, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    last_seen_at: Mapped[Optional[str]] = mapped_column(String)

    user: Mapped[User] = relationship()


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint(BOOL_CHECK.format("is_deleted"), name="projects_deleted_bool"),
        CheckConstraint(
            "planned_end IS NULL OR planned_start IS NULL OR planned_end >= planned_start",
            name="projects_period",
        ),
        Index("idx_projects_status", "status"),
        Index("idx_projects_period", "planned_start", "planned_end"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String)
    planned_start: Mapped[Optional[str]] = mapped_column(String)
    planned_end: Mapped[Optional[str]] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, nullable=False)
    revision: Mapped[int] = mapped_column(default=1, nullable=False)
    is_deleted: Mapped[int] = mapped_column(default=0, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))


class ProjectEditor(Base):
    __tablename__ = "project_editors"
    __table_args__ = (
        PrimaryKeyConstraint("project_id", "user_id"),
    )

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)

    project: Mapped[Project] = relationship()
    user: Mapped[User] = relationship()


class Part(Base):
    __tablename__ = "parts"
    __table_args__ = (
        CheckConstraint("weight > 0 AND weight <= 1", name="parts_weight"),
        CheckConstraint(BOOL_CHECK.format("is_deleted"), name="parts_deleted_bool"),
        CheckConstraint(
            "planned_end IS NULL OR planned_start IS NULL OR planned_end >= planned_start",
            name="parts_period",
        ),
        Index("idx_parts_project_sort", "project_id", "sort_order"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    weight: Mapped[float] = mapped_column(nullable=False)
    planned_start: Mapped[Optional[str]] = mapped_column(String)
    planned_end: Mapped[Optional[str]] = mapped_column(String)
    sort_order: Mapped[int] = mapped_column(default=0, nullable=False)
    is_deleted: Mapped[int] = mapped_column(default=0, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)


class Unit(Base):
    __tablename__ = "units"
    __table_args__ = (
        CheckConstraint(BOOL_CHECK.format("is_active"), name="units_active_bool"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    code: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    is_active: Mapped[int] = mapped_column(default=1, nullable=False)
    sort_order: Mapped[int] = mapped_column(default=0, nullable=False)


class WorkItem(Base):
    __tablename__ = "work_items"
    __table_args__ = (
        CheckConstraint("total_quantity >= 0", name="work_items_total_quantity"),
        CheckConstraint("weight > 0 AND weight <= 1", name="work_items_weight"),
        CheckConstraint(BOOL_CHECK.format("is_deleted"), name="work_items_deleted_bool"),
        CheckConstraint(
            "planned_end IS NULL OR planned_start IS NULL OR planned_end >= planned_start",
            name="work_items_period",
        ),
        Index("idx_work_items_part_sort", "part_id", "sort_order"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    part_id: Mapped[str] = mapped_column(ForeignKey("parts.id", ondelete="RESTRICT"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    total_quantity: Mapped[float] = mapped_column(nullable=False)
    unit_id: Mapped[str] = mapped_column(ForeignKey("units.id", ondelete="RESTRICT"), nullable=False)
    weight: Mapped[float] = mapped_column(nullable=False)
    planned_start: Mapped[Optional[str]] = mapped_column(String)
    planned_end: Mapped[Optional[str]] = mapped_column(String)
    sort_order: Mapped[int] = mapped_column(default=0, nullable=False)
    is_deleted: Mapped[int] = mapped_column(default=0, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)


class Assignment(Base):
    __tablename__ = "assignments"
    __table_args__ = (
        CheckConstraint("allocated_quantity >= 0", name="assignments_allocated_quantity"),
        CheckConstraint(BOOL_CHECK.format("is_deleted"), name="assignments_deleted_bool"),
        UniqueConstraint("work_item_id", "user_id", name="uq_assignments_work_item_user"),
        Index("idx_assignments_work_item", "work_item_id"),
        Index("idx_assignments_user", "user_id"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    work_item_id: Mapped[str] = mapped_column(ForeignKey("work_items.id", ondelete="RESTRICT"), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    allocated_quantity: Mapped[float] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String, default="ACTIVE", nullable=False)
    is_deleted: Mapped[int] = mapped_column(default=0, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)


class AssignmentProgress(Base):
    __tablename__ = "assignment_progress"
    __table_args__ = (
        CheckConstraint("completed_quantity >= 0", name="assignment_progress_completed_quantity"),
        CheckConstraint(
            "schedule_end IS NULL OR schedule_start IS NULL OR schedule_end >= schedule_start",
            name="assignment_progress_period",
        ),
        Index("idx_assignment_progress_user", "user_id"),
    )

    assignment_id: Mapped[str] = mapped_column(
        ForeignKey("assignments.id", ondelete="RESTRICT"), primary_key=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    schedule_start: Mapped[Optional[str]] = mapped_column(String)
    schedule_end: Mapped[Optional[str]] = mapped_column(String)
    completed_quantity: Mapped[float] = mapped_column(default=0, nullable=False)
    note: Mapped[Optional[str]] = mapped_column(String)
    revision: Mapped[int] = mapped_column(default=1, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)
    device_id: Mapped[Optional[str]] = mapped_column(ForeignKey("devices.id", ondelete="RESTRICT"))

    assignment: Mapped[Assignment] = relationship()


class ProgressHistory(Base):
    __tablename__ = "progress_history"
    __table_args__ = (
        CheckConstraint("current_quantity >= 0", name="progress_history_current_quantity"),
        Index("idx_progress_history_assignment_time", "assignment_id", "created_at"),
        Index("idx_progress_history_user_time", "user_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    assignment_id: Mapped[str] = mapped_column(ForeignKey("assignments.id", ondelete="RESTRICT"), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    previous_quantity: Mapped[float] = mapped_column(nullable=False)
    delta_quantity: Mapped[float] = mapped_column(nullable=False)
    current_quantity: Mapped[float] = mapped_column(nullable=False)
    note: Mapped[Optional[str]] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    device_id: Mapped[Optional[str]] = mapped_column(ForeignKey("devices.id", ondelete="RESTRICT"))


class CalendarEvent(Base):
    __tablename__ = "calendar_events"
    __table_args__ = (
        CheckConstraint("event_type IN ('MEETING', 'ABSENCE', 'OTHER')", name="calendar_events_type"),
        CheckConstraint("visibility IN ('PRIVATE', 'TEAM')", name="calendar_events_visibility"),
        CheckConstraint(BOOL_CHECK.format("is_deleted"), name="calendar_events_deleted_bool"),
        CheckConstraint("end_at IS NULL OR end_at >= start_at", name="calendar_events_period"),
        Index("idx_calendar_user_period", "user_id", "start_at", "end_at"),
        Index("idx_calendar_visibility_start", "visibility", "start_at"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    start_at: Mapped[str] = mapped_column(String, nullable=False)
    end_at: Mapped[Optional[str]] = mapped_column(String)
    visibility: Mapped[str] = mapped_column(String, nullable=False)
    memo: Mapped[Optional[str]] = mapped_column(String)
    revision: Mapped[int] = mapped_column(default=1, nullable=False)
    is_deleted: Mapped[int] = mapped_column(default=0, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)


class PersonalNote(Base):
    __tablename__ = "personal_notes"
    __table_args__ = (
        CheckConstraint(BOOL_CHECK.format("is_pinned"), name="personal_notes_pinned_bool"),
        CheckConstraint(BOOL_CHECK.format("is_deleted"), name="personal_notes_deleted_bool"),
        Index("idx_personal_notes_user_pin", "user_id", "is_pinned", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[Optional[str]] = mapped_column(String)
    is_pinned: Mapped[int] = mapped_column(default=0, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)
    is_deleted: Mapped[int] = mapped_column(default=0, nullable=False)


class AppMeta(Base):
    __tablename__ = "app_meta"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[Optional[str]] = mapped_column(String)


class SyncState(Base):
    __tablename__ = "sync_state"
    __table_args__ = (
        PrimaryKeyConstraint("source_type", "source_id"),
    )

    source_type: Mapped[str] = mapped_column(String, nullable=False)
    source_id: Mapped[str] = mapped_column(String, nullable=False)
    remote_revision: Mapped[int] = mapped_column(default=0, nullable=False)
    last_sync_at: Mapped[Optional[str]] = mapped_column(String)
    last_hash: Mapped[Optional[str]] = mapped_column(String)


class SyncOutbox(Base):
    __tablename__ = "sync_outbox"
    __table_args__ = (
        UniqueConstraint("target_type", "target_id", name="uq_sync_outbox_target"),
        Index("idx_sync_outbox_retry", "next_retry_at"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    target_type: Mapped[str] = mapped_column(String, nullable=False)
    target_id: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    retry_count: Mapped[int] = mapped_column(default=0, nullable=False)
    next_retry_at: Mapped[Optional[str]] = mapped_column(String)
    last_error: Mapped[Optional[str]] = mapped_column(String)
