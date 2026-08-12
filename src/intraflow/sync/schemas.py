from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


SCHEMA_VERSION = 3
Id = Annotated[str, Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")]
UtcTimestamp = Annotated[str, Field(pattern=r"^.+Z$")]
DateValue = Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")]


class SnapshotModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SnapshotBase(SnapshotModel):
    schema_version: Literal[1, 2, 3] = SCHEMA_VERSION
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
    is_active: bool = True
    is_deleted: bool
    created_at: UtcTimestamp
    updated_at: UtcTimestamp


class WorkItemData(SnapshotModel):
    id: Id
    part_id: Id
    owner_user_id: Id | None = None
    name: str = Field(min_length=1)
    description: str | None = None
    total_quantity: float = Field(ge=0)
    unit_id: Id
    weight: float = Field(gt=0, le=1)
    planned_start: DateValue | None = None
    planned_end: DateValue | None = None
    sort_order: int
    is_active: bool = True
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
    # v2 compatibility only. These aliases are accepted but never exposed or serialized.
    legacy_schedule_start: DateValue | None = Field(
        default=None, validation_alias="schedule_start", exclude=True, repr=False,
    )
    legacy_schedule_end: DateValue | None = Field(
        default=None, validation_alias="schedule_end", exclude=True, repr=False,
    )
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


class _LegacyCalendarEventData(SnapshotModel):
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
    # Kept for reading v1 snapshots; v2 project snapshots leave these empty.
    work_items: list[WorkItemData] = Field(default_factory=list)
    assignments: list[AssignmentData] = Field(default_factory=list)


class UserPublicSnapshot(SnapshotBase):
    source_type: Literal["USER_PUBLIC"] = "USER_PUBLIC"
    user_id: Id
    work_items: list[WorkItemData] = Field(default_factory=list)
    assignments: list[AssignmentData] = Field(default_factory=list)
    progress: list[AssignmentProgressData]
    progress_history: list[ProgressHistoryData]
    legacy_team_calendar_events: list[_LegacyCalendarEventData] = Field(
        default_factory=list, validation_alias="team_calendar_events", exclude=True, repr=False,
    )


Snapshot = Annotated[
    Union[SystemConfigSnapshot, UsersSnapshot, UnitsSnapshot, ProjectSnapshot, UserPublicSnapshot],
    Field(discriminator="source_type"),
]
snapshot_adapter = TypeAdapter(Snapshot)
