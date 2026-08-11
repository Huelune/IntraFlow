from __future__ import annotations

import pytest
from sqlalchemy.orm import Session, sessionmaker

from intraflow.services.progress_service import ProgressService
from intraflow.services.team_view_service import TeamViewFilters, TeamViewService
from workflow import build_workflow


def test_calendar_uses_actual_schedule_and_optional_planned_overlay(
    session_factory: sessionmaker[Session],
) -> None:
    identity, _admin, _work, _project, _part, item = build_workflow(session_factory)
    ProgressService(
        session_factory, current_user_id=identity.user_id, current_device_id=identity.device_id,
    ).set_schedule(item.assignment_id, "2026-08-03", "2026-08-10")
    service = TeamViewService(session_factory, current_user_id=identity.user_id)

    actual = service.list_calendar_entries(
        "2026-08-05", "2026-08-05", include_planned=False)
    combined = service.list_calendar_entries(
        "2026-08-05", "2026-08-05", include_planned=True)

    assert [(x.start_date, x.end_date, x.source) for x in actual] == [
        ("2026-08-03", "2026-08-10", "ACTUAL"),
    ]
    assert {x.source for x in combined} == {"ACTUAL", "PLANNED"}
    assert service.list_calendar_entries(
        "2026-08-01", "2026-08-01", include_planned=False) == []


def test_progress_overview_normalizes_work_and_part_weights(
    session_factory: sessionmaker[Session],
) -> None:
    identity, admin, work, project_id, part_id, item = build_workflow(session_factory)
    unit_id = admin.list_units()[0].id
    admin.update_part(part_id, "파트", 0.25, "2026-08-01", "2026-08-31")
    work.update_my_work_item(
        item.work_item_id, item.name, item.description, 10, unit_id, 0.25,
        item.planned_start, item.planned_end,
    )
    second_id = work.create_my_work_item(
        part_id, "완료 업무", None, 10, unit_id, 0.75, "2026-08-02", "2026-08-20")
    second = work.get_my_work_item(second_id)
    part2 = admin.create_part(project_id, "두 번째 파트", 0.75, "2026-08-01", "2026-08-31")
    work.create_my_work_item(part2, "미시작 업무", None, 10, unit_id, 1, "2026-08-02", "2026-08-20")
    progress = ProgressService(
        session_factory, current_user_id=identity.user_id, current_device_id=identity.device_id)
    progress.set_completed_quantity(item.assignment_id, 5)
    progress.set_completed_quantity(second.assignment_id, 10)

    overview = TeamViewService(session_factory, current_user_id=identity.user_id).get_progress_overview()

    first_part = next(x for x in overview.projects[0].children if x.id == part_id)
    assert first_part.progress_ratio == pytest.approx(0.875)
    assert overview.projects[0].progress_ratio == pytest.approx(0.21875)
    assert overview.active_project_count == 1
    assert overview.active_work_count == 3
    assert overview.completed_work_count == 1


def test_progress_excludes_inactive_by_default_and_flags_zero_target(
    session_factory: sessionmaker[Session],
) -> None:
    identity, _admin, work, _project, part_id, item = build_workflow(session_factory)
    unit_id = work.active_units()[0][0]
    zero_id = work.create_my_work_item(
        part_id, "목표량 없음", None, 0, unit_id, 1, "2026-08-02", "2026-08-20")
    work.set_my_work_item_active(item.work_item_id, False)
    service = TeamViewService(session_factory, current_user_id=identity.user_id)

    default = service.get_progress_overview()
    included = service.get_progress_overview(TeamViewFilters(include_inactive=True))

    assert default.active_work_count == 1
    assert default.warning_count == 1
    assert default.projects[0].children[0].progress_ratio is None
    assert included.projects[0].total_count == 2
    assert any(node.id == zero_id for node in included.projects[0].children[0].children)
