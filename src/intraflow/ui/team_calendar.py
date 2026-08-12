from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from intraflow.services.team_view_service import TeamCalendarEntry


class _DayCell(QFrame):
    dateClicked = Signal(QDate)
    workClicked = Signal(QDate, str)

    def __init__(self) -> None:
        super().__init__()
        self.setProperty("calendarDay", True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.date = QDate()
        self.date_label = QLabel()
        self.date_label.setProperty("calendarDate", True)
        self.entries_layout = QVBoxLayout()
        self.entries_layout.setContentsMargins(0, 0, 0, 0)
        self.entries_layout.setSpacing(2)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 4, 5, 4)
        layout.setSpacing(3)
        layout.addWidget(self.date_label)
        layout.addLayout(self.entries_layout)
        layout.addStretch(1)

    def set_content(
        self,
        date: QDate,
        *,
        in_month: bool,
        selected: bool,
        entries: Iterable[TeamCalendarEntry],
    ) -> None:
        self.date = date
        self.date_label.setText(str(date.day()))
        self.setProperty("outsideMonth", not in_month)
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)
        self.date_label.style().unpolish(self.date_label)
        self.date_label.style().polish(self.date_label)

        while self.entries_layout.count():
            item = self.entries_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        values = list(entries)
        for entry in values[:3]:
            button = QToolButton()
            button.setProperty("calendarEntry", True)
            button.setProperty("wide", True)
            button.setProperty("calendarSource", entry.source.lower())
            button.setProperty("deadline", date.toString("yyyy-MM-dd") == entry.end_date)
            suffix = QDate.fromString(entry.end_date, "yyyy-MM-dd").toString("M/d")
            prefix = "마감 · " if button.property("deadline") else ""
            button.setText(f"{prefix}{entry.work_name} · ~{suffix}")
            source = {"ACTUAL": "개인 일정", "PLANNED": "계획 일정", "BOTH": "개인·계획 일정"}[entry.source]
            button.setToolTip(
                f"{entry.owner_name}\n{entry.path}\n{source}: "
                f"{entry.start_date} ~ {entry.end_date}\n진행률 {entry.progress_ratio:.0%}"
            )
            button.clicked.connect(
                lambda _checked=False, work_id=entry.work_item_id: self.workClicked.emit(
                    self.date, work_id,
                ),
            )
            self.entries_layout.addWidget(button)

        if len(values) > 3:
            more = QToolButton()
            more.setProperty("calendarEntry", True)
            more.setProperty("wide", True)
            more.setProperty("calendarMore", True)
            more.setText(f"+{len(values) - 3}개")
            more.setToolTip("이 날짜의 전체 업무를 아래 목록에서 봅니다.")
            more.clicked.connect(lambda: self.dateClicked.emit(self.date))
            self.entries_layout.addWidget(more)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self.dateClicked.emit(self.date)
        super().mousePressEvent(event)


class TeamMonthCalendar(QWidget):
    """Month calendar that renders work names directly inside each date cell."""

    selectionChanged = Signal()
    currentPageChanged = Signal(int, int)
    workActivated = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        today = QDate.currentDate()
        self._year, self._month = today.year(), today.month()
        self._selected_date = today
        self._entries: list[TeamCalendarEntry] = []

        previous = QToolButton()
        previous.setText("‹")
        previous.setToolTip("이전 달")
        previous.setProperty("calendarNav", True)
        next_button = QToolButton()
        next_button.setText("›")
        next_button.setToolTip("다음 달")
        next_button.setProperty("calendarNav", True)
        self.month_label = QLabel()
        self.month_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.month_label.setProperty("calendarMonth", True)
        previous.clicked.connect(lambda: self._move_month(-1))
        next_button.clicked.connect(lambda: self._move_month(1))

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.addWidget(previous)
        header.addWidget(self.month_label, 1)
        header.addWidget(next_button)

        self.grid = QGridLayout()
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(2)
        self.grid.setVerticalSpacing(2)
        for column, text in enumerate(("일", "월", "화", "수", "목", "금", "토")):
            label = QLabel(text)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setProperty("calendarWeekday", True)
            label.setProperty("weekend", column in (0, 6))
            self.grid.addWidget(label, 0, column)
            self.grid.setColumnStretch(column, 1)

        self.cells: list[_DayCell] = []
        for row in range(6):
            self.grid.setRowStretch(row + 1, 1)
            for column in range(7):
                cell = _DayCell()
                cell.dateClicked.connect(self.setSelectedDate)
                cell.workClicked.connect(self._activate_work)
                self.cells.append(cell)
                self.grid.addWidget(cell, row + 1, column)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addLayout(header)
        layout.addLayout(self.grid, 1)
        self.setMinimumHeight(420)
        self._render()

    def yearShown(self) -> int:
        return self._year

    def monthShown(self) -> int:
        return self._month

    def selectedDate(self) -> QDate:
        return QDate(self._selected_date)

    def setSelectedDate(self, date: QDate) -> None:
        if not date.isValid():
            return
        page_changed = (date.year(), date.month()) != (self._year, self._month)
        selection_changed = date != self._selected_date
        self._selected_date = QDate(date)
        if page_changed:
            self._year, self._month = date.year(), date.month()
            self.currentPageChanged.emit(self._year, self._month)
        self._render()
        if selection_changed:
            self.selectionChanged.emit()

    def set_entries(self, entries: Iterable[TeamCalendarEntry]) -> None:
        self._entries = list(entries)
        self._render()

    def _move_month(self, offset: int) -> None:
        target = QDate(self._year, self._month, 1).addMonths(offset)
        selected_day = min(self._selected_date.day(), target.daysInMonth())
        self._year, self._month = target.year(), target.month()
        self._selected_date = QDate(self._year, self._month, selected_day)
        self.currentPageChanged.emit(self._year, self._month)
        self.selectionChanged.emit()
        self._render()

    def _activate_work(self, date: QDate, work_item_id: str) -> None:
        self.setSelectedDate(date)
        self.workActivated.emit(work_item_id)

    def _render(self) -> None:
        self.month_label.setText(f"{self._year}년 {self._month}월")
        first = QDate(self._year, self._month, 1)
        start = first.addDays(-(first.dayOfWeek() % 7))
        entries_by_date: dict[str, list[TeamCalendarEntry]] = {}
        for entry in self._entries:
            day = QDate.fromString(entry.start_date, "yyyy-MM-dd")
            end = QDate.fromString(entry.end_date, "yyyy-MM-dd")
            while day.isValid() and day <= end:
                entries_by_date.setdefault(day.toString("yyyy-MM-dd"), []).append(entry)
                day = day.addDays(1)
        for index, cell in enumerate(self.cells):
            date = start.addDays(index)
            cell.set_content(
                date,
                in_month=date.month() == self._month,
                selected=date == self._selected_date,
                entries=entries_by_date.get(date.toString("yyyy-MM-dd"), ()),
            )
