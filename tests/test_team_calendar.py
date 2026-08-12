from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QApplication, QToolButton

from intraflow.services.team_view_service import TeamCalendarEntry
from intraflow.ui.team_calendar import TeamMonthCalendar


def _entry(index: int, *, end_date: str = "2026-08-12") -> TeamCalendarEntry:
    return TeamCalendarEntry(
        work_item_id=f"work-{index}", assignment_id=f"assignment-{index}",
        owner_name="담당자", project_name="긴 프로젝트", part_name="긴 파트",
        work_name=f"업무 {index}", start_date="2026-08-10", end_date=end_date,
        source="PLANNED" if index % 2 else "ACTUAL", progress_ratio=0.25,
        progress_state="IN_PROGRESS", effective_active=True, date_warning=False,
    )


def test_month_calendar_shows_three_tasks_and_overflow() -> None:
    app = QApplication.instance() or QApplication([])
    calendar = TeamMonthCalendar()
    calendar.setSelectedDate(QDate(2026, 8, 11))
    calendar.set_entries([_entry(index) for index in range(5)])
    app.processEvents()

    selected_cell = next(cell for cell in calendar.cells if cell.date == QDate(2026, 8, 11))
    buttons = selected_cell.findChildren(QToolButton)
    assert [button.text() for button in buttons[:3]] == [
        "업무 0 · ~8/12", "업무 1 · ~8/12", "업무 2 · ~8/12",
    ]
    assert buttons[3].text() == "+2개"
    assert selected_cell.property("selected") is True


def test_month_calendar_marks_deadline_and_activates_work() -> None:
    QApplication.instance() or QApplication([])
    calendar = TeamMonthCalendar()
    calendar.setSelectedDate(QDate(2026, 8, 12))
    calendar.set_entries([_entry(1)])
    selected: list[str] = []
    calendar.workActivated.connect(selected.append)

    cell = next(value for value in calendar.cells if value.date == QDate(2026, 8, 12))
    button = cell.findChild(QToolButton)
    assert button.text().startswith("마감 · ")
    button.click()

    assert selected == ["work-1"]
