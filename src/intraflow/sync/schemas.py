from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


SCHEMA_VERSION = 1
Id = Annotated[str, Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")]
UtcTimestamp = Annotated[str, Field(pattern=r"^.+Z$")]
DateValue = Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")]


class SnapshotModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SnapshotBase(SnapshotModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    revision: int = Field(ge=0)
    generated_at: UtcTimestamp


class UserData(SnapshotModel):
    id: Id
    user_code: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    department: str | None = None
    is_system_admin: bool
    is_active: bool
    created_at: UtcTimestamp
    updated_at: UtcTimestamp
    revision: int = Field(ge=1)


class UnitData(SnapshotModel):
    id: Id
    code: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    is_active: bool
    sort_order: int


class ProjectData(SnapshotModel):
    id: Id
    name: str = Field(min_length=1)
    description: str | None = None
    planned_start: DateValue | None = None
    planned_end: DateValue | None = None
    status: str = Field(min_length=1)
    revision: int = Field(ge=1)
    is_deleted: bool
    created_at: UtcTimestamp
    updated_at: UtcTimestamp
    updated_by: Id | None = None


class PartData(SnapshotModel):
    id: Id
    project_id: Id
    name: str = Field(min_length=1)
    weight: float = Field(gt=0, le=1)
    planned_start: DateValue | None = None
    planned_end: DateValue | None = None
    sort_order: int
    is_deleted: bool
    created_at: UtcTimestamp
    updated_at: UtcTimestamp


class WorkItemData(SnapshotModel):
    id: Id
    part_id: Id
    name: str = Field(min_length=1)
    total_quantity: float = Field(ge=0)
    unit_id: Id
    weight: float = Field(gt=0, le=1)
    planned_start: DateValue | None = None
    planned_end: DateValue | None = None
    sort_order: int
    is_deleted: bool
    created_at: UtcTimestamp
    updated_at: UtcTimestamp


class AssignmentData(SnapshotModel):
    id: Id
    work_item_id: Id
    user_id: Id
    allocated_quantity: float = Field(ge=0)
    status: str = Field(min_length=1)
    is_deleted: bool
    created_at: UtcTimestamp
    updated_at: UtcTimestamp


class AssignmentProgressData(SnapshotModel):
    assignment_id: Id
    user_id: Id
    schedule_start: DateValue | None = None
    schedule_end: DateValue | None = None
    completed_quantity: float = Field(ge=0)
    note: str | None = None
    revision: int = Field(ge=1)
    updated_at: UtcTimestamp
    device_id: Id | None = None


class ProgressHistoryData(SnapshotModel):
    id: Id
    assignment_id: Id
    user_id: Id
    previous_quantity: float = Field(ge=0)
    delta_quantity: float
    current_quantity: float = Field(ge=0)
    note: str | None = None
    created_at: UtcTimestamp
    device_id: Id | None = None


class CalendarEventData(SnapshotModel):
    id: Id
    user_id: Id
    title: str = Field(min_length=1)
    event_type: Literal["MEETING", "ABSENCE", "OTHER"]
    start_at: UtcTimestamp
    end_at: UtcTimestamp | None = None
    visibility: Literal["TEAM"]
    memo: str | None = None
    revision: int = Field(ge=1)
    is_deleted: bool
    created_at: UtcTimestamp
    updated_at: UtcTimestamp


class SystemConfigSnapshot(SnapshotBase):
    source_type: Literal["SYSTEM_CONFIG"] = "SYSTEM_CONFIG"
    values: dict[str, str]


class UsersSnapshot(SnapshotBase):
    source_type: Literal["USERS"] = "USERS"
    users: list[UserData]


class UnitsSnapshot(SnapshotBase):
    source_type: Literal["UNITS"] = "UNITS"
    units: list[UnitData]


class ProjectSnapshot(SnapshotBase):
    source_type: Literal["PROJECT"] = "PROJECT"
    project: ProjectData
    editor_user_ids: list[Id]
    parts: list[PartData]
    work_items: list[WorkItemData]
    assignments: list[AssignmentData]


class UserPublicSnapshot(SnapshotBase):
    source_type: Literal["USER_PUBLIC"] = "USER_PUBLIC"
    user_id: Id
    progress: list[AssignmentProgressData]
    progress_history: list[ProgressHistoryData]
    team_calendar_events: list[CalendarEventData]


Snapshot = Annotated[
    Union[SystemConfigSnapshot, UsersSnapshot, UnitsSnapshot, ProjectSnapshot, UserPublicSnapshot],
    Field(discriminator="source_type"),
]
snapshot_adapter = TypeAdapter(Snapshot)
