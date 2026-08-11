from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QProgressBar, QPushButton, QSplitter, QTableWidget,
    QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

from intraflow.services.errors import IntraFlowError
from intraflow.services.progress_service import ProgressService
from intraflow.services.work_service import WorkService


def date_edit() -> QDateEdit:
    value = QDateEdit(QDate.currentDate())
    value.setCalendarPopup(True)
    value.setDisplayFormat("yyyy-MM-dd")
    return value


class MyWorkWidget(QWidget):
    def __init__(self, work: WorkService, progress: ProgressService, on_changed: Callable[[], None]) -> None:
        super().__init__()
        self.work, self.progress, self.on_changed = work, progress, on_changed
        self.current_item_id: str | None = None
        self.current_assignment_id: str | None = None
        self.include_inactive = QCheckBox("비활성 포함")
        self.include_inactive.toggled.connect(self.refresh)
        self.filter_project, self.filter_part, self.filter_progress = QComboBox(), QComboBox(), QComboBox()
        self.filter_progress.addItem("전체 진행 상태", "ALL")
        self.filter_progress.addItem("미시작", "NOT_STARTED")
        self.filter_progress.addItem("진행 중", "IN_PROGRESS")
        self.filter_progress.addItem("완료", "DONE")
        for combo in (self.filter_project, self.filter_part, self.filter_progress):
            combo.currentIndexChanged.connect(self.refresh)
        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(
            ["업무", "프로젝트", "파트", "상태", "완료량", "목표량", "진행률", "일정", "최신 메모"]
        )
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.itemSelectionChanged.connect(self._load_selection)
        self.table.horizontalHeader().setStretchLastSection(True)

        self.project = QComboBox()
        self.part = QComboBox()
        self.project.currentIndexChanged.connect(self._refresh_parts)
        self.name = QLineEdit()
        self.description = QTextEdit()
        self.description.setMaximumHeight(70)
        self.unit = QComboBox()
        self.quantity = _quantity(1_000_000, 1)
        self.weight = _quantity(1, 1)
        self.start, self.end = date_edit(), date_edit()
        new_button, save_button = QPushButton("새 업무"), QPushButton("업무 저장")
        toggle_button, delete_button = QPushButton("ON/OFF"), QPushButton("업무 삭제")
        new_button.clicked.connect(self.new_item)
        save_button.clicked.connect(self.save_item)
        toggle_button.clicked.connect(self.toggle_item)
        delete_button.clicked.connect(self.delete_item)

        definition = QFormLayout()
        definition.addRow("프로젝트", self.project)
        definition.addRow("파트", self.part)
        definition.addRow("업무명", self.name)
        definition.addRow("설명", self.description)
        definition.addRow("단위", self.unit)
        definition.addRow("목표 수량", self.quantity)
        definition.addRow("가중치", self.weight)
        definition.addRow("시작일", self.start)
        definition.addRow("종료일", self.end)
        definition_actions = QHBoxLayout()
        for button in (new_button, save_button, toggle_button, delete_button):
            definition_actions.addWidget(button)
        definition.addRow(definition_actions)

        self.big_progress = QProgressBar()
        self.big_progress.setRange(0, 100)
        self.delta = _quantity(1_000_000, 0, minimum=-1_000_000)
        self.absolute = _quantity(1_000_000, 0)
        apply_delta, apply_absolute = QPushButton("증감량 반영"), QPushButton("현재 완료량 설정")
        apply_delta.clicked.connect(self.apply_delta)
        apply_absolute.clicked.connect(self.apply_absolute)
        self.note = QTextEdit()
        self.note.setMaximumHeight(70)
        save_note, clear_note = QPushButton("메모 저장"), QPushButton("메모 지우기")
        save_note.clicked.connect(lambda: self.save_note(False))
        clear_note.clicked.connect(lambda: self.save_note(True))
        self.schedule_start, self.schedule_end = date_edit(), date_edit()
        save_schedule = QPushButton("개인 일정 저장")
        save_schedule.clicked.connect(self.save_schedule)
        self.result = QLabel()
        self.history = QTableWidget(0, 6)
        self.history.setHorizontalHeaderLabels(["시각", "이전량", "증감량", "현재량", "진행률", "메모"])
        self.history.horizontalHeader().setStretchLastSection(True)
        progress_form = QFormLayout()
        progress_form.addRow("진행률", self.big_progress)
        progress_form.addRow("이번 증감량", self.delta)
        progress_form.addRow("", apply_delta)
        progress_form.addRow("현재 완료량", self.absolute)
        progress_form.addRow("", apply_absolute)
        progress_form.addRow("메모", self.note)
        note_actions = QHBoxLayout()
        note_actions.addWidget(save_note)
        note_actions.addWidget(clear_note)
        progress_form.addRow(note_actions)
        progress_form.addRow("개인 시작일", self.schedule_start)
        progress_form.addRow("개인 종료일", self.schedule_end)
        progress_form.addRow("", save_schedule)
        progress_form.addRow(self.result)

        detail = QWidget()
        detail_layout = QVBoxLayout(detail)
        detail_layout.addLayout(definition)
        detail_layout.addLayout(progress_form)
        detail_layout.addWidget(QLabel("진행·메모 이력"))
        detail_layout.addWidget(self.history, stretch=1)
        splitter = QSplitter()
        list_area = QWidget()
        list_layout = QVBoxLayout(list_area)
        filters = QHBoxLayout()
        filters.addWidget(self.filter_project)
        filters.addWidget(self.filter_part)
        filters.addWidget(self.filter_progress)
        filters.addWidget(self.include_inactive)
        list_layout.addLayout(filters)
        list_layout.addWidget(self.table)
        splitter.addWidget(list_area)
        splitter.addWidget(detail)
        splitter.setSizes([760, 420])
        layout = QVBoxLayout(self)
        layout.addWidget(splitter)
        self.refresh()

    def refresh(self) -> None:
        selected = self.current_item_id
        all_rows = self.work.list_my_work_items(include_inactive=True)
        self._refresh_filters(all_rows)
        rows = [item for item in all_rows if self._matches_filters(item)]
        if not self.include_inactive.isChecked():
            rows = [item for item in rows if item.effective_active]
        self._refresh_choices()
        self.table.setRowCount(len(rows))
        selected_row = -1
        for row_index, item in enumerate(rows):
            schedule = " ~ ".join(x for x in (item.schedule_start, item.schedule_end) if x) or "-"
            state = "일정 경고" if item.date_warning else ("활성" if item.effective_active else "비활성")
            values = [item.name, item.project_name, item.part_name,
                      state, f"{item.completed_quantity:g}",
                      f"{item.total_quantity:g}", "", schedule, item.note or ""]
            for column, text in enumerate(values):
                if column == 6:
                    bar = QProgressBar()
                    bar.setRange(0, 100)
                    bar.setValue(round(item.progress_ratio * 100))
                    self.table.setCellWidget(row_index, column, bar)
                    continue
                cell = QTableWidgetItem(text)
                if column == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, item.work_item_id)
                    cell.setData(Qt.ItemDataRole.UserRole + 1, item.assignment_id)
                self.table.setItem(row_index, column, cell)
            if item.work_item_id == selected:
                selected_row = row_index
        if selected_row >= 0:
            self.table.selectRow(selected_row)
        elif rows:
            self.table.selectRow(0)
        else:
            self.new_item()

    def select_item(self, work_item_id: str) -> None:
        self.current_item_id = work_item_id
        self.include_inactive.setChecked(True)
        self.refresh()

    def _refresh_filters(self, rows) -> None:
        project_id, part_id = self.filter_project.currentData(), self.filter_part.currentData()
        projects = sorted({(item.project_id, item.project_name) for item in rows}, key=lambda x: x[1])
        parts = sorted({(item.part_id, item.part_name) for item in rows
                        if not project_id or item.project_id == project_id}, key=lambda x: x[1])
        _fill_filter(self.filter_project, "전체 프로젝트", projects, project_id)
        _fill_filter(self.filter_part, "전체 파트", parts, part_id)

    def _matches_filters(self, item) -> bool:
        project_id, part_id = self.filter_project.currentData(), self.filter_part.currentData()
        progress = self.filter_progress.currentData()
        if project_id and item.project_id != project_id:
            return False
        if part_id and item.part_id != part_id:
            return False
        if progress == "NOT_STARTED" and item.completed_quantity != 0:
            return False
        if progress == "IN_PROGRESS" and not (0 < item.completed_quantity < item.total_quantity):
            return False
        if progress == "DONE" and item.completed_quantity < item.total_quantity:
            return False
        return True

    def new_item(self) -> None:
        self.current_item_id = self.current_assignment_id = None
        self.name.clear()
        self.description.clear()
        self.quantity.setValue(1)
        self.weight.setValue(1)
        self.note.clear()
        self.history.setRowCount(0)
        self._refresh_parts()

    def save_item(self) -> None:
        try:
            values = (self.name.text(), self.description.toPlainText(), self.quantity.value(),
                      self.unit.currentData(), self.weight.value(), _date(self.start), _date(self.end))
            if self.current_item_id:
                self.work.update_my_work_item(self.current_item_id, *values)
            else:
                self.current_item_id = self.work.create_my_work_item(self.part.currentData(), *values)
        except IntraFlowError as exc:
            QMessageBox.warning(self, "업무 저장 실패", str(exc))
            return
        self.on_changed()

    def toggle_item(self) -> None:
        if not self.current_item_id:
            return
        item = self.work.get_my_work_item(self.current_item_id)
        self._run(lambda: self.work.set_my_work_item_active(item.work_item_id, not item.is_active))

    def delete_item(self) -> None:
        if not self.current_item_id:
            return
        if QMessageBox.question(self, "업무 삭제", "선택한 업무를 삭제할까요? 진행 이력은 보존됩니다.") != QMessageBox.StandardButton.Yes:
            return
        self._run(lambda: self.work.delete_my_work_item(self.current_item_id))
        self.current_item_id = self.current_assignment_id = None

    def apply_delta(self) -> None:
        if not self.current_assignment_id:
            return
        self._progress_run(lambda: self.progress.add_delta(self.current_assignment_id, self.delta.value()))

    def apply_absolute(self) -> None:
        if not self.current_assignment_id:
            return
        self._progress_run(lambda: self.progress.set_completed_quantity(self.current_assignment_id, self.absolute.value()))

    def save_note(self, clear: bool) -> None:
        if self.current_assignment_id:
            self._progress_run(lambda: self.progress.set_note(
                self.current_assignment_id, None if clear else self.note.toPlainText()))

    def save_schedule(self) -> None:
        if self.current_assignment_id:
            self._progress_run(lambda: self.progress.set_schedule(
                self.current_assignment_id, _date(self.schedule_start), _date(self.schedule_end)))

    def _progress_run(self, action) -> None:
        try:
            result = action()
        except IntraFlowError as exc:
            QMessageBox.warning(self, "진행 상태 저장 실패", str(exc))
            return
        self.result.setText(
            f"{result.previous_quantity:g} → {result.current_quantity:g} ({result.progress_ratio:.0%})")
        self.delta.setValue(0)
        self.on_changed()

    def _run(self, action) -> None:
        try:
            action()
        except IntraFlowError as exc:
            QMessageBox.warning(self, "처리 실패", str(exc))
            return
        self.on_changed()

    def _load_selection(self) -> None:
        row = self.table.currentRow()
        cell = self.table.item(row, 0) if row >= 0 else None
        if cell is None:
            return
        self.current_item_id = cell.data(Qt.ItemDataRole.UserRole)
        self.current_assignment_id = cell.data(Qt.ItemDataRole.UserRole + 1)
        item = self.work.get_my_work_item(self.current_item_id)
        _select(self.project, item.project_id)
        self._refresh_parts()
        _select(self.part, item.part_id)
        _select(self.unit, item.unit_id)
        self.name.setText(item.name)
        self.description.setPlainText(item.description or "")
        self.quantity.setValue(item.total_quantity)
        self.weight.setValue(item.weight)
        _set_date(self.start, item.planned_start)
        _set_date(self.end, item.planned_end)
        _set_date(self.schedule_start, item.schedule_start or item.planned_start)
        _set_date(self.schedule_end, item.schedule_end or item.planned_end)
        self.absolute.setValue(item.completed_quantity)
        self.note.setPlainText(item.note or "")
        self.big_progress.setValue(round(item.progress_ratio * 100))
        histories = self.progress.list_history(item.assignment_id)
        self.history.setRowCount(len(histories))
        for row_index, history in enumerate(histories):
            ratio = history.current_quantity / item.total_quantity if item.total_quantity else 0
            for column, value in enumerate([
                history.created_at, f"{history.previous_quantity:g}", f"{history.delta_quantity:g}",
                f"{history.current_quantity:g}", f"{ratio:.0%}", history.note or "",
            ]):
                self.history.setItem(row_index, column, QTableWidgetItem(value))

    def _refresh_choices(self) -> None:
        project_id, unit_id = self.project.currentData(), self.unit.currentData()
        _fill_combo(self.project, self.work.active_projects(), project_id)
        _fill_combo(self.unit, self.work.active_units(), unit_id)
        self._refresh_parts()

    def _refresh_parts(self) -> None:
        current = self.part.currentData()
        parts = self.work.parts_for_project(self.project.currentData()) if self.project.currentData() else []
        _fill_combo(self.part, [(x[0], x[1]) for x in parts], current)
        selected = next((x for x in parts if x[0] == self.part.currentData()), None)
        if selected:
            _set_date(self.start, selected[2])
            _set_date(self.end, selected[3])


class TeamWorkWidget(QWidget):
    def __init__(self, work: WorkService, open_my_work: Callable[[str], None]) -> None:
        super().__init__()
        self.work, self.open_my_work = work, open_my_work
        self.filter_user, self.filter_project, self.filter_part, self.filter_progress = (
            QComboBox(), QComboBox(), QComboBox(), QComboBox())
        self.include_inactive = QCheckBox("비활성 포함")
        self.filter_progress.addItem("전체 진행 상태", "ALL")
        self.filter_progress.addItem("미시작", "NOT_STARTED")
        self.filter_progress.addItem("진행 중", "IN_PROGRESS")
        self.filter_progress.addItem("완료", "DONE")
        for combo in (self.filter_user, self.filter_project, self.filter_part, self.filter_progress):
            combo.currentIndexChanged.connect(self.refresh)
        self.include_inactive.toggled.connect(self.refresh)
        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(
            ["소유자", "프로젝트", "파트", "업무", "일정", "완료량", "목표량", "진행률", "최신 메모"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.updated = QLabel()
        open_button = QPushButton("내 업무에서 열기")
        open_button.clicked.connect(self._open_selected)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("팀 업무는 읽기 전용입니다."))
        filters = QHBoxLayout()
        for widget in (self.filter_user, self.filter_project, self.filter_part,
                       self.filter_progress, self.include_inactive):
            filters.addWidget(widget)
        layout.addLayout(filters)
        layout.addWidget(self.table)
        layout.addWidget(open_button)
        layout.addWidget(self.updated)
        self.refresh()

    def refresh(self) -> None:
        all_rows = self.work.list_team_work_items(include_inactive=True)
        self._refresh_filters(all_rows)
        rows = [item for item in all_rows if self._matches_filters(item)]
        if not self.include_inactive.isChecked():
            rows = [item for item in rows if item.effective_active]
        self.table.setRowCount(len(rows))
        latest = "-"
        for row_index, item in enumerate(rows):
            latest = max(latest, item.updated_at)
            values = [item.owner_name, item.project_name, item.part_name, item.name,
                      f"{item.planned_start or '-'} ~ {item.planned_end or '-'}",
                      f"{item.completed_quantity:g}", f"{item.total_quantity:g}", "", item.note or ""]
            for column, value in enumerate(values):
                if column == 7:
                    bar = QProgressBar()
                    bar.setRange(0, 100)
                    bar.setValue(round(item.progress_ratio * 100))
                    self.table.setCellWidget(row_index, column, bar)
                else:
                    cell = QTableWidgetItem(value)
                    if column == 3:
                        cell.setData(Qt.ItemDataRole.UserRole, item.work_item_id)
                        cell.setData(Qt.ItemDataRole.UserRole + 1, item.owner_user_id)
                    self.table.setItem(row_index, column, cell)
        self.updated.setText(f"마지막 로컬 반영 시각: {latest}")

    def _refresh_filters(self, rows) -> None:
        values = (
            (self.filter_user, "전체 사용자", {(x.owner_user_id, x.owner_name) for x in rows}),
            (self.filter_project, "전체 프로젝트", {(x.project_id, x.project_name) for x in rows}),
            (self.filter_part, "전체 파트", {(x.part_id, x.part_name) for x in rows}),
        )
        for combo, label, choices in values:
            _fill_filter(combo, label, sorted(choices, key=lambda x: x[1]), combo.currentData())

    def _matches_filters(self, item) -> bool:
        if self.filter_user.currentData() and item.owner_user_id != self.filter_user.currentData():
            return False
        if self.filter_project.currentData() and item.project_id != self.filter_project.currentData():
            return False
        if self.filter_part.currentData() and item.part_id != self.filter_part.currentData():
            return False
        progress = self.filter_progress.currentData()
        return not (
            (progress == "NOT_STARTED" and item.completed_quantity != 0)
            or (progress == "IN_PROGRESS" and not (0 < item.completed_quantity < item.total_quantity))
            or (progress == "DONE" and item.completed_quantity < item.total_quantity)
        )

    def _open_selected(self) -> None:
        row = self.table.currentRow()
        cell = self.table.item(row, 3) if row >= 0 else None
        if cell is not None and cell.data(Qt.ItemDataRole.UserRole + 1) == self.work.current_user_id:
            self.open_my_work(cell.data(Qt.ItemDataRole.UserRole))
        elif cell is not None:
            QMessageBox.information(self, "읽기 전용 업무", "다른 사용자의 업무는 내 업무에서 열 수 없습니다.")


def _quantity(maximum: float, default: float, *, minimum: float = 0) -> QDoubleSpinBox:
    value = QDoubleSpinBox()
    value.setRange(minimum, maximum)
    value.setDecimals(3)
    value.setValue(default)
    return value


def _date(widget: QDateEdit) -> str:
    return widget.date().toString("yyyy-MM-dd")


def _set_date(widget: QDateEdit, value: str | None) -> None:
    if value:
        widget.setDate(QDate.fromString(value, "yyyy-MM-dd"))


def _fill_combo(combo: QComboBox, values: list[tuple[str, str]], selected: str | None = None) -> None:
    combo.blockSignals(True)
    combo.clear()
    for identity, label in values:
        combo.addItem(label, identity)
    _select(combo, selected)
    combo.blockSignals(False)


def _fill_filter(combo: QComboBox, label: str, values: list[tuple[str, str]], selected: str | None) -> None:
    combo.blockSignals(True)
    combo.clear()
    combo.addItem(label, None)
    for identity, text in values:
        combo.addItem(text, identity)
    _select(combo, selected)
    combo.blockSignals(False)


def _select(combo: QComboBox, identity: str | None) -> None:
    index = combo.findData(identity)
    if index >= 0:
        combo.setCurrentIndex(index)
