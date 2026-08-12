from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from intraflow.models import Assignment, AssignmentProgress, Part, Project, User, WorkItem
from intraflow.services.errors import PermissionDeniedError


@dataclass(frozen=True, slots=True)
class TeamViewFilters:
    user_id: str | None = None
    project_id: str | None = None
    part_id: str | None = None
    include_inactive: bool = False


@dataclass(frozen=True, slots=True)
class TeamCalendarEntry:
    work_item_id: str
    assignment_id: str
    owner_name: str
    project_name: str
    part_name: str
    work_name: str
    start_date: str
    end_date: str
    source: str
    progress_ratio: float
    progress_state: str
    effective_active: bool
    date_warning: bool

    @property
    def path(self) -> str:
        return f"{self.project_name} / {self.part_name} / {self.work_name}"


@dataclass(frozen=True, slots=True)
class TeamProgressNode:
    node_type: str
    id: str
    label: str
    status: str
    progress_ratio: float | None
    total_count: int
    completed_count: int
    in_progress_count: int
    not_started_count: int
    warning_count: int
    last_updated: str | None
    children: tuple["TeamProgressNode", ...] = ()


@dataclass(frozen=True, slots=True)
class TeamProgressOverview:
    active_project_count: int
    active_work_count: int
    completed_work_count: int
    warning_count: int
    projects: tuple[TeamProgressNode, ...]


@dataclass(frozen=True, slots=True)
class _WorkRow:
    item: WorkItem
    assignment: Assignment
    progress: AssignmentProgress | None
    part: Part
    project: Project
    user: User

    @property
    def completed(self) -> float:
        return float(self.progress.completed_quantity) if self.progress else 0.0

    @property
    def ratio(self) -> float:
        total = float(self.item.total_quantity)
        return min(1.0, self.completed / total) if total > 0 else 0.0

    @property
    def progress_state(self) -> str:
        if float(self.item.total_quantity) > 0 and self.completed >= float(self.item.total_quantity):
            return "DONE"
        if self.completed > 0:
            return "IN_PROGRESS"
        return "NOT_STARTED"

    @property
    def effective_active(self) -> bool:
        return bool(
            self.item.is_active and self.part.is_active and self.project.status == "ACTIVE"
            and self.assignment.status == "ACTIVE" and self.user.is_active
        )

    @property
    def warning(self) -> bool:
        return bool(
            float(self.item.total_quantity) <= 0
            or self.item.planned_start < self.part.planned_start
            or self.item.planned_end > self.part.planned_end
        )

    @property
    def updated_at(self) -> str:
        return self.progress.updated_at if self.progress else self.item.updated_at


class TeamViewService:
    """Build read-only calendar and weighted progress views from shared work data."""

    def __init__(self, session_factory: sessionmaker[Session], *, current_user_id: str) -> None:
        self.session_factory = session_factory
        self.current_user_id = current_user_id

    def list_calendar_entries(
        self, start_date: str, end_date: str, *,
        filters: TeamViewFilters = TeamViewFilters(),
    ) -> list[TeamCalendarEntry]:
        rows = self._rows(filters)
        entries: list[TeamCalendarEntry] = []
        for row in rows:
            actual = None
            if row.progress and row.progress.schedule_start and row.progress.schedule_end:
                actual = (row.progress.schedule_start, row.progress.schedule_end)
            planned = (row.item.planned_start, row.item.planned_end)
            periods: list[tuple[str, str, str]] = []
            if actual:
                source = "BOTH" if actual == planned else "ACTUAL"
                periods.append((actual[0], actual[1], source))
            if planned != actual:
                periods.append((planned[0], planned[1], "PLANNED"))
            for period_start, period_end, source in periods:
                if period_end < start_date or period_start > end_date:
                    continue
                entries.append(TeamCalendarEntry(
                    work_item_id=row.item.id, assignment_id=row.assignment.id,
                    owner_name=row.user.display_name, project_name=row.project.name,
                    part_name=row.part.name, work_name=row.item.name,
                    start_date=period_start, end_date=period_end, source=source,
                    progress_ratio=row.ratio, progress_state=row.progress_state,
                    effective_active=row.effective_active, date_warning=row.warning,
                ))
        return sorted(entries, key=lambda x: (x.start_date, x.owner_name, x.path, x.source))

    def get_progress_overview(
        self, filters: TeamViewFilters = TeamViewFilters(),
    ) -> TeamProgressOverview:
        rows = self._rows(filters)
        project_groups: dict[str, list[_WorkRow]] = {}
        for row in rows:
            project_groups.setdefault(row.project.id, []).append(row)
        project_nodes: list[TeamProgressNode] = []
        for project_rows in project_groups.values():
            part_groups: dict[str, list[_WorkRow]] = {}
            for row in project_rows:
                part_groups.setdefault(row.part.id, []).append(row)
            part_nodes = [self._part_node(group) for group in part_groups.values()]
            valid_parts = [
                (node, float(group[0].part.weight))
                for node, group in ((node, part_groups[node.id]) for node in part_nodes)
                if node.progress_ratio is not None
            ]
            denominator = sum(weight for _node, weight in valid_parts)
            ratio = (sum(node.progress_ratio * weight for node, weight in valid_parts) / denominator
                     if denominator else None)
            project = project_rows[0].project
            project_nodes.append(self._aggregate_node(
                "PROJECT", project.id, project.name, project.status, ratio,
                project_rows, tuple(part_nodes),
            ))
        project_nodes.sort(key=lambda x: x.label)
        active_rows = [row for row in rows if row.effective_active]
        return TeamProgressOverview(
            active_project_count=len({row.project.id for row in active_rows}),
            active_work_count=len(active_rows),
            completed_work_count=sum(row.progress_state == "DONE" for row in active_rows),
            warning_count=sum(row.warning for row in rows),
            projects=tuple(project_nodes),
        )

    def _part_node(self, rows: list[_WorkRow]) -> TeamProgressNode:
        work_nodes = tuple(self._work_node(row) for row in rows)
        valid = [row for row in rows if float(row.item.total_quantity) > 0]
        denominator = sum(float(row.item.weight) for row in valid)
        ratio = (sum(row.ratio * float(row.item.weight) for row in valid) / denominator
                 if denominator else None)
        part, project = rows[0].part, rows[0].project
        status = "ACTIVE" if part.is_active and project.status == "ACTIVE" else "INACTIVE"
        return self._aggregate_node("PART", part.id, part.name, status, ratio, rows, work_nodes)

    def _work_node(self, row: _WorkRow) -> TeamProgressNode:
        ratio = row.ratio if float(row.item.total_quantity) > 0 else None
        return TeamProgressNode(
            node_type="WORK", id=row.item.id, label=row.item.name,
            status="ACTIVE" if row.effective_active else "INACTIVE", progress_ratio=ratio,
            total_count=1, completed_count=int(row.progress_state == "DONE"),
            in_progress_count=int(row.progress_state == "IN_PROGRESS"),
            not_started_count=int(row.progress_state == "NOT_STARTED"),
            warning_count=int(row.warning), last_updated=row.updated_at,
        )

    @staticmethod
    def _aggregate_node(
        node_type: str, identity: str, label: str, status: str, ratio: float | None,
        rows: list[_WorkRow], children: tuple[TeamProgressNode, ...],
    ) -> TeamProgressNode:
        return TeamProgressNode(
            node_type=node_type, id=identity, label=label, status=status, progress_ratio=ratio,
            total_count=len(rows), completed_count=sum(x.progress_state == "DONE" for x in rows),
            in_progress_count=sum(x.progress_state == "IN_PROGRESS" for x in rows),
            not_started_count=sum(x.progress_state == "NOT_STARTED" for x in rows),
            warning_count=sum(x.warning for x in rows),
            last_updated=max((x.updated_at for x in rows), default=None), children=children,
        )

    def _rows(self, filters: TeamViewFilters) -> list[_WorkRow]:
        statement = (
            select(WorkItem, Assignment, AssignmentProgress, Part, Project, User)
            .join(Assignment, Assignment.work_item_id == WorkItem.id)
            .outerjoin(AssignmentProgress, AssignmentProgress.assignment_id == Assignment.id)
            .join(Part, WorkItem.part_id == Part.id)
            .join(Project, Part.project_id == Project.id)
            .join(User, WorkItem.owner_user_id == User.id)
            .where(WorkItem.is_deleted == 0, Assignment.is_deleted == 0,
                   Part.is_deleted == 0, Project.is_deleted == 0,
                   Assignment.user_id == WorkItem.owner_user_id)
            .order_by(Project.name, Part.sort_order, Part.name, WorkItem.sort_order, WorkItem.name)
        )
        if filters.user_id:
            statement = statement.where(WorkItem.owner_user_id == filters.user_id)
        if filters.project_id:
            statement = statement.where(Project.id == filters.project_id)
        if filters.part_id:
            statement = statement.where(Part.id == filters.part_id)
        if not filters.include_inactive:
            statement = statement.where(
                WorkItem.is_active == 1, Assignment.status == "ACTIVE", Part.is_active == 1,
                Project.status == "ACTIVE", User.is_active == 1,
            )
        with self.session_factory() as session:
            current = session.get(User, self.current_user_id)
            if current is None or not current.is_active:
                raise PermissionDeniedError("활성 사용자만 팀 현황을 조회할 수 있습니다.")
            return [_WorkRow(*row) for row in session.execute(statement).all()]
