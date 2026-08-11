from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QDoubleSpinBox, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QMessageBox, QProgressBar, QPushButton, QScrollArea, QSplitter, QStyle,
    QTableWidget, QTableWidgetItem, QTextEdit, QToolButton, QVBoxLayout, QWidget,
)

from intraflow.services.errors import IntraFlowError
from intraflow.services.progress_service import ProgressService
from intraflow.services.work_service import WorkItemView, WorkService
from intraflow.ui.dialogs import WorkItemDialog


def date_edit() -> QDateEdit:
    value = QDateEdit(QDate.currentDate())
    value.setCalendarPopup(True)
    value.setDisplayFormat("yyyy-MM-dd")
    return value


class WorkDetailPanel(QWidget):
    def __init__(self, *, owner_mode: bool) -> None:
        super().__init__()
        self.owner_mode = owner_mode
        self.current_item: WorkItemView | None = None
        self.inputs_dirty = False
        self.setProperty("card", True)
        self.title = QLabel("업무를 선택하세요")
        self.title.setProperty("role", "title")
        self.path = QLabel()
        self.path.setProperty("role", "muted")
        self.description = QLabel("선택한 업무의 상세 정보가 여기에 표시됩니다.")
        self.description.setWordWrap(True)
        self.owner, self.unit, self.period, self.state, self.updated, self.local_refreshed = (
            QLabel() for _ in range(6))
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.quantity = QLabel()
        self.refresh_button = self._tool_button(QStyle.StandardPixmap.SP_BrowserReload, "새로고침")
        self.edit_button = self._tool_button(QStyle.StandardPixmap.SP_FileDialogDetailedView, "업무 수정")
        self.delete_button = self._tool_button(QStyle.StandardPixmap.SP_TrashIcon, "업무 삭제", danger=True)
        self.open_my_button = QPushButton("내 업무에서 열기")
        actions = QHBoxLayout()
        actions.addWidget(self.refresh_button)
        actions.addStretch()
        actions.addWidget(self.open_my_button)
        actions.addWidget(self.edit_button)
        actions.addWidget(self.delete_button)
        summary = QGridLayout()
        summary.setHorizontalSpacing(10)
        summary.setVerticalSpacing(5)
        summary.addWidget(_muted("소유자"), 0, 0)
        summary.addWidget(self.owner, 0, 1)
        summary.addWidget(_muted("단위"), 0, 2)
        summary.addWidget(self.unit, 0, 3)
        summary.addWidget(_muted("계획 기간"), 1, 0)
        summary.addWidget(self.period, 1, 1)
        summary.addWidget(_muted("상태"), 1, 2)
        summary.addWidget(self.state, 1, 3)
        summary.addWidget(_muted("마지막 반영"), 2, 0)
        summary.addWidget(self.updated, 2, 1)
        summary.addWidget(_muted("로컬 갱신"), 2, 2)
        summary.addWidget(self.local_refreshed, 2, 3)
        summary.addWidget(_muted("완료량 / 목표량"), 3, 0)
        summary.addWidget(self.quantity, 3, 1, 1, 3)
        summary.addWidget(self.progress, 4, 0, 1, 4)
        summary.setColumnStretch(1, 1)
        summary.setColumnStretch(3, 1)
        self.history = QTableWidget(0, 6)
        self.history.setHorizontalHeaderLabels(["시각", "이전량", "증감량", "현재량", "진행률", "메모"])
        self.history.horizontalHeader().setStretchLastSection(True)
        self.history.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.history.setAlternatingRowColors(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(7)
        layout.addLayout(actions)
        layout.addWidget(self.title)
        layout.addWidget(self.path)
        layout.addWidget(self.description)
        layout.addLayout(summary)
        if owner_mode:
            self._build_owner_inputs(layout)
        self.history_toggle = QToolButton()
        self.history_toggle.setText("진행·메모 이력")
        self.history_toggle.setProperty("wide", True)
        self.history_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.history_toggle.setArrowType(Qt.ArrowType.DownArrow)
        self.history_toggle.setCheckable(True)
        self.history_toggle.setChecked(True)
        self.history_toggle.toggled.connect(self._toggle_history)
        layout.addWidget(self.history_toggle)
        layout.addWidget(self.history, stretch=1)
        self.clear()

    def _build_owner_inputs(self, layout: QVBoxLayout) -> None:
        self.delta = _quantity(1_000_000, 0, minimum=-1_000_000)
        self.absolute = _quantity(1_000_000, 0)
        self.apply_delta_button, self.apply_absolute_button = QPushButton("반영"), QPushButton("완료량 저장")
        self.apply_delta_button.setProperty("primary", True)
        self.note = QTextEdit()
        self.note.setMaximumHeight(64)
        self.save_note_button, self.clear_note_button = QPushButton("저장"), QPushButton("지우기")
        self.schedule_start, self.schedule_end = date_edit(), date_edit()
        self.save_schedule_button = QPushButton("일정 저장")
        self.result = QLabel()
        self.result.setProperty("status", "active")
        progress_form = QGridLayout()
        progress_form.setHorizontalSpacing(7)
        progress_form.setVerticalSpacing(6)
        note_row = QHBoxLayout()
        note_row.addWidget(self.save_note_button)
        note_row.addWidget(self.clear_note_button)
        progress_form.addWidget(_muted("증감량"), 0, 0)
        progress_form.addWidget(self.delta, 0, 1)
        progress_form.addWidget(self.apply_delta_button, 0, 2)
        progress_form.addWidget(_muted("완료량"), 0, 3)
        progress_form.addWidget(self.absolute, 0, 4)
        progress_form.addWidget(self.apply_absolute_button, 0, 5)
        progress_form.addWidget(_muted("현재 메모"), 1, 0)
        progress_form.addWidget(self.note, 1, 1, 1, 5)
        progress_form.addLayout(note_row, 2, 1, 1, 5)
        progress_form.addWidget(_muted("개인 일정"), 3, 0)
        progress_form.addWidget(self.schedule_start, 3, 1)
        progress_form.addWidget(QLabel("~"), 3, 2)
        progress_form.addWidget(self.schedule_end, 3, 3)
        progress_form.addWidget(self.save_schedule_button, 3, 4, 1, 2)
        progress_form.addWidget(self.result, 4, 0, 1, 6)
        progress_form.setColumnStretch(1, 1)
        progress_form.setColumnStretch(4, 1)
        layout.addWidget(_section("진행 상태 바로 입력"))
        layout.addLayout(progress_form)
        self.delta.valueChanged.connect(self._mark_dirty)
        self.absolute.valueChanged.connect(self._mark_dirty)
        self.note.textChanged.connect(self._mark_dirty)
        self.schedule_start.dateChanged.connect(self._mark_dirty)
        self.schedule_end.dateChanged.connect(self._mark_dirty)

    def _tool_button(
        self, icon: QStyle.StandardPixmap, tooltip: str, *, danger: bool = False,
    ) -> QToolButton:
        button = QToolButton()
        button.setIcon(self.style().standardIcon(icon))
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        if danger:
            button.setProperty("danger", True)
        return button

    def _toggle_history(self, visible: bool) -> None:
        self.history.setVisible(visible)
        self.history_toggle.setArrowType(
            Qt.ArrowType.DownArrow if visible else Qt.ArrowType.RightArrow)

    def clear(self, message: str = "선택한 업무의 상세 정보가 여기에 표시됩니다.") -> None:
        self.current_item = None
        self.title.setText("업무를 선택하세요")
        self.path.clear()
        self.description.setText(message)
        for label in (self.owner, self.unit, self.period, self.state, self.quantity,
                      self.updated, self.local_refreshed):
            label.clear()
        self.progress.setValue(0)
        self.history.setRowCount(0)
        self.edit_button.setVisible(False)
        self.delete_button.setVisible(False)
        self.open_my_button.setVisible(False)

    def load(self, item: WorkItemView, histories, *, force_inputs: bool = False, show_open_my: bool = False) -> None:
        changed = self.current_item is None or self.current_item.work_item_id != item.work_item_id
        self.current_item = item
        self.title.setText(item.name)
        self.path.setText(item.path)
        self.description.setText(item.description or "설명 없음")
        self.owner.setText(item.owner_name)
        self.unit.setText(item.unit_name)
        self.period.setText(f"{item.planned_start} ~ {item.planned_end}")
        state = "일정 경고" if item.date_warning else ("활성" if item.effective_active else "비활성")
        self.state.setText(state)
        self.state.setProperty("status", "warning" if item.date_warning else ("active" if item.effective_active else ""))
        self.state.style().unpolish(self.state)
        self.state.style().polish(self.state)
        self.quantity.setText(f"{item.completed_quantity:g} / {item.total_quantity:g}")
        self.progress.setValue(round(item.progress_ratio * 100))
        self.updated.setText(item.updated_at)
        self.local_refreshed.setText(datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"))
        self.edit_button.setVisible(self.owner_mode)
        self.delete_button.setVisible(self.owner_mode)
        self.open_my_button.setVisible(show_open_my)
        if self.owner_mode and (changed or force_inputs or not self.inputs_dirty):
            widgets = (self.delta, self.absolute, self.note, self.schedule_start, self.schedule_end)
            for widget in widgets:
                widget.blockSignals(True)
            self.delta.setValue(0)
            self.absolute.setValue(item.completed_quantity)
            self.note.setPlainText(item.note or "")
            _set_date(self.schedule_start, item.schedule_start or item.planned_start)
            _set_date(self.schedule_end, item.schedule_end or item.planned_end)
            for widget in widgets:
                widget.blockSignals(False)
            self.inputs_dirty = False
        self.history.setRowCount(len(histories))
        for row_index, history in enumerate(histories):
            ratio = history.current_quantity / item.total_quantity if item.total_quantity else 0
            values = [history.created_at, f"{history.previous_quantity:g}", f"{history.delta_quantity:g}",
                      f"{history.current_quantity:g}", f"{ratio:.0%}", history.note or ""]
            for column, value in enumerate(values):
                self.history.setItem(row_index, column, QTableWidgetItem(value))

    def _mark_dirty(self, *_args) -> None:
        self.inputs_dirty = True


class MyWorkWidget(QWidget):
    def __init__(self, work: WorkService, progress: ProgressService, on_changed: Callable[[], None]) -> None:
        super().__init__()
        self.work, self.progress, self.on_changed = work, progress, on_changed
        self.current_item_id: str | None = None
        self.current_assignment_id: str | None = None
        self.include_inactive = QCheckBox("비활성 포함")
        self.filter_project, self.filter_part, self.filter_progress = QComboBox(), QComboBox(), QComboBox()
        for text, value in (("전체 진행 상태", "ALL"), ("미시작", "NOT_STARTED"),
                            ("진행 중", "IN_PROGRESS"), ("완료", "DONE")):
            self.filter_progress.addItem(text, value)
        for widget in (self.filter_project, self.filter_part, self.filter_progress):
            widget.currentIndexChanged.connect(self.refresh)
        self.include_inactive.toggled.connect(self.refresh)
        self.add_button = QPushButton("새 업무")
        self.add_button.setProperty("primary", True)
        self.add_button.clicked.connect(self.add_item)
        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(
            ["업무", "프로젝트", "파트", "상태", "완료량", "목표량", "진행률", "일정", "최신 메모"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._load_selection)
        self.detail = WorkDetailPanel(owner_mode=True)
        self.detail.refresh_button.clicked.connect(self.manual_refresh)
        self.detail.edit_button.clicked.connect(self.edit_item)
        self.detail.delete_button.clicked.connect(self.delete_item)
        self.detail.apply_delta_button.clicked.connect(self.apply_delta)
        self.detail.apply_absolute_button.clicked.connect(self.apply_absolute)
        self.detail.save_note_button.clicked.connect(lambda: self.save_note(False))
        self.detail.clear_note_button.clicked.connect(lambda: self.save_note(True))
        self.detail.save_schedule_button.clicked.connect(self.save_schedule)
        filters = QHBoxLayout()
        filters.addWidget(self.filter_project)
        filters.addWidget(self.filter_part)
        filters.addWidget(self.filter_progress)
        filters.addWidget(self.include_inactive)
        filters.addStretch()
        filters.addWidget(self.add_button)
        list_card = QWidget()
        list_card.setProperty("card", True)
        list_card.setMinimumWidth(420)
        list_layout = QVBoxLayout(list_card)
        list_layout.setContentsMargins(12, 12, 12, 12)
        list_layout.addLayout(filters)
        list_layout.addWidget(self.table)
        splitter = QSplitter()
        splitter.addWidget(list_card)
        splitter.addWidget(_detail_scroll(self.detail))
        splitter.setSizes([620, 620])
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        splitter.setCollapsible(1, False)
        layout = QVBoxLayout(self)
        layout.addWidget(splitter)
        self.refresh()

    def refresh(
        self, _signal_value: object = None, *, automatic: bool = False, force_inputs: bool = False,
    ) -> None:
        selected, scroll = self.current_item_id, self.table.verticalScrollBar().value()
        had_selection = selected is not None
        all_rows = self.work.list_my_work_items(include_inactive=True)
        self._refresh_filters(all_rows)
        rows = [item for item in all_rows if self._matches_filters(item)]
        if not self.include_inactive.isChecked():
            rows = [item for item in rows if item.effective_active]
        self.table.blockSignals(True)
        self.table.setRowCount(len(rows))
        selected_row = -1
        for row_index, item in enumerate(rows):
            schedule = f"{item.schedule_start or '-'} ~ {item.schedule_end or '-'}"
            state = "일정 경고" if item.date_warning else ("활성" if item.effective_active else "비활성")
            values = [item.name, item.project_name, item.part_name, state, f"{item.completed_quantity:g}",
                      f"{item.total_quantity:g}", "", schedule, item.note or ""]
            _set_work_row(self.table, row_index, item, values, progress_column=6, id_column=0)
            if item.work_item_id == selected:
                selected_row = row_index
        if selected_row < 0 and rows and not had_selection:
            selected_row = 0
        if selected_row >= 0:
            self.table.selectRow(selected_row)
            selected = rows[selected_row].work_item_id
        self.table.blockSignals(False)
        self.table.verticalScrollBar().setValue(scroll)
        if selected:
            self.current_item_id = selected
            self._load_detail(force_inputs=force_inputs)
        else:
            self.current_item_id = self.current_assignment_id = None
            message = ("선택한 업무가 현재 필터에서 제외되었거나 삭제되었습니다."
                       if had_selection else "표시할 업무가 없습니다.")
            self.detail.clear(message)

    def manual_refresh(self) -> None:
        if self.detail.inputs_dirty:
            answer = QMessageBox.question(self, "입력값 새로고침", "저장하지 않은 입력값을 버리고 새로고침할까요?")
            if answer != QMessageBox.StandardButton.Yes:
                self._load_detail(force_inputs=False)
                return
        self.refresh(automatic=False, force_inputs=True)

    def add_item(self) -> None:
        dialog = WorkItemDialog(self.work)
        if dialog.exec() == dialog.DialogCode.Accepted:
            self.on_changed()

    def edit_item(self) -> None:
        if not self.current_item_id:
            return
        dialog = WorkItemDialog(self.work, self.work.get_my_work_item(self.current_item_id))
        if dialog.exec() == dialog.DialogCode.Accepted:
            self.on_changed()

    def delete_item(self) -> None:
        if not self.current_item_id:
            return
        if QMessageBox.question(self, "업무 삭제", "선택한 업무를 삭제할까요? 진행 이력은 보존됩니다.") != QMessageBox.StandardButton.Yes:
            return
        self._run(lambda: self.work.delete_my_work_item(self.current_item_id))
        self.current_item_id = self.current_assignment_id = None

    def apply_delta(self) -> None:
        if self.current_assignment_id:
            self._progress_run(lambda: self.progress.add_delta(self.current_assignment_id, self.detail.delta.value()))

    def apply_absolute(self) -> None:
        if self.current_assignment_id:
            self._progress_run(lambda: self.progress.set_completed_quantity(
                self.current_assignment_id, self.detail.absolute.value()))

    def save_note(self, clear: bool) -> None:
        if self.current_assignment_id:
            self._progress_run(lambda: self.progress.set_note(
                self.current_assignment_id, None if clear else self.detail.note.toPlainText()))

    def save_schedule(self) -> None:
        if self.current_assignment_id:
            self._progress_run(lambda: self.progress.set_schedule(
                self.current_assignment_id, _date(self.detail.schedule_start), _date(self.detail.schedule_end)))

    def select_item(self, work_item_id: str) -> None:
        self.current_item_id = work_item_id
        self.include_inactive.setChecked(True)
        self.refresh()

    def _progress_run(self, action) -> None:
        try:
            result = action()
        except IntraFlowError as exc:
            QMessageBox.warning(self, "진행 상태 저장 실패", str(exc))
            return
        self.detail.result.setText(
            f"{result.previous_quantity:g} → {result.current_quantity:g} ({result.progress_ratio:.0%})")
        self.detail.inputs_dirty = False
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
        changed = self.current_item_id != cell.data(Qt.ItemDataRole.UserRole)
        self.current_item_id = cell.data(Qt.ItemDataRole.UserRole)
        self.current_assignment_id = cell.data(Qt.ItemDataRole.UserRole + 1)
        self._load_detail(force_inputs=changed)

    def _load_detail(self, *, force_inputs: bool) -> None:
        if not self.current_item_id:
            self.detail.clear()
            return
        try:
            item = self.work.get_my_work_item(self.current_item_id)
            histories = self.progress.list_history(item.assignment_id)
        except IntraFlowError:
            self.detail.clear()
            return
        self.current_assignment_id = item.assignment_id
        self.detail.load(item, histories, force_inputs=force_inputs)

    def _refresh_filters(self, rows) -> None:
        project_id, part_id = self.filter_project.currentData(), self.filter_part.currentData()
        projects = sorted({(x.project_id, x.project_name) for x in rows}, key=lambda x: x[1])
        parts = sorted({(x.part_id, x.part_name) for x in rows if not project_id or x.project_id == project_id},
                       key=lambda x: x[1])
        _fill_filter(self.filter_project, "전체 프로젝트", projects, project_id)
        _fill_filter(self.filter_part, "전체 파트", parts, part_id)

    def _matches_filters(self, item: WorkItemView) -> bool:
        if self.filter_project.currentData() and item.project_id != self.filter_project.currentData():
            return False
        if self.filter_part.currentData() and item.part_id != self.filter_part.currentData():
            return False
        progress = self.filter_progress.currentData()
        return not ((progress == "NOT_STARTED" and item.completed_quantity != 0)
                    or (progress == "IN_PROGRESS" and not 0 < item.completed_quantity < item.total_quantity)
                    or (progress == "DONE" and item.completed_quantity < item.total_quantity))


class TeamWorkWidget(QWidget):
    def __init__(
        self, work: WorkService, progress: ProgressService, open_my_work: Callable[[str], None],
    ) -> None:
        super().__init__()
        self.work, self.progress, self.open_my_work = work, progress, open_my_work
        self.current_item_id: str | None = None
        self.filter_user, self.filter_project, self.filter_part, self.filter_progress = (
            QComboBox(), QComboBox(), QComboBox(), QComboBox())
        self.include_inactive = QCheckBox("비활성 포함")
        for text, value in (("전체 진행 상태", "ALL"), ("미시작", "NOT_STARTED"),
                            ("진행 중", "IN_PROGRESS"), ("완료", "DONE")):
            self.filter_progress.addItem(text, value)
        for widget in (self.filter_user, self.filter_project, self.filter_part, self.filter_progress):
            widget.currentIndexChanged.connect(self.refresh)
        self.include_inactive.toggled.connect(self.refresh)
        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(
            ["소유자", "프로젝트", "파트", "업무", "일정", "완료량", "목표량", "진행률", "최신 메모"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._load_selection)
        self.detail = WorkDetailPanel(owner_mode=False)
        self.detail.refresh_button.clicked.connect(self.refresh)
        self.detail.open_my_button.clicked.connect(self._open_selected)
        filters = QHBoxLayout()
        for widget in (self.filter_user, self.filter_project, self.filter_part,
                       self.filter_progress, self.include_inactive):
            filters.addWidget(widget)
        list_card = QWidget()
        list_card.setProperty("card", True)
        list_card.setMinimumWidth(420)
        list_layout = QVBoxLayout(list_card)
        list_layout.setContentsMargins(12, 12, 12, 12)
        list_layout.addLayout(filters)
        list_layout.addWidget(self.table)
        splitter = QSplitter()
        splitter.addWidget(list_card)
        splitter.addWidget(_detail_scroll(self.detail))
        splitter.setSizes([620, 620])
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        splitter.setCollapsible(1, False)
        layout = QVBoxLayout(self)
        layout.addWidget(splitter)
        self.refresh()

    def refresh(self, _signal_value: object = None, *, automatic: bool = False) -> None:
        selected, scroll = self.current_item_id, self.table.verticalScrollBar().value()
        had_selection = selected is not None
        all_rows = self.work.list_team_work_items(include_inactive=True)
        self._refresh_filters(all_rows)
        rows = [x for x in all_rows if self._matches_filters(x)]
        if not self.include_inactive.isChecked():
            rows = [x for x in rows if x.effective_active]
        self.table.blockSignals(True)
        self.table.setRowCount(len(rows))
        selected_row = -1
        for row_index, item in enumerate(rows):
            values = [item.owner_name, item.project_name, item.part_name, item.name,
                      f"{item.planned_start} ~ {item.planned_end}", f"{item.completed_quantity:g}",
                      f"{item.total_quantity:g}", "", item.note or ""]
            _set_work_row(self.table, row_index, item, values, progress_column=7, id_column=3)
            if item.work_item_id == selected:
                selected_row = row_index
        if selected_row < 0 and rows and not had_selection:
            selected_row = 0
        if selected_row >= 0:
            self.table.selectRow(selected_row)
            selected = rows[selected_row].work_item_id
        self.table.blockSignals(False)
        self.table.verticalScrollBar().setValue(scroll)
        self.current_item_id = selected if selected_row >= 0 else None
        if self.current_item_id:
            self._load_detail()
        else:
            message = ("선택한 업무가 현재 필터에서 제외되었거나 삭제되었습니다."
                       if had_selection else "표시할 팀 업무가 없습니다.")
            self.detail.clear(message)

    def _load_selection(self) -> None:
        row = self.table.currentRow()
        cell = self.table.item(row, 3) if row >= 0 else None
        self.current_item_id = cell.data(Qt.ItemDataRole.UserRole) if cell else None
        self._load_detail()

    def _load_detail(self) -> None:
        if not self.current_item_id:
            self.detail.clear()
            return
        try:
            item = self.work.get_team_work_item(self.current_item_id)
            histories = self.progress.list_public_history(item.assignment_id)
        except IntraFlowError:
            self.detail.clear()
            return
        self.detail.load(item, histories, show_open_my=item.owner_user_id == self.work.current_user_id)

    def _open_selected(self) -> None:
        if self.current_item_id:
            self.open_my_work(self.current_item_id)

    def _refresh_filters(self, rows) -> None:
        values = ((self.filter_user, "전체 사용자", {(x.owner_user_id, x.owner_name) for x in rows}),
                  (self.filter_project, "전체 프로젝트", {(x.project_id, x.project_name) for x in rows}),
                  (self.filter_part, "전체 파트", {(x.part_id, x.part_name) for x in rows}))
        for combo, label, choices in values:
            _fill_filter(combo, label, sorted(choices, key=lambda x: x[1]), combo.currentData())

    def _matches_filters(self, item: WorkItemView) -> bool:
        if self.filter_user.currentData() and item.owner_user_id != self.filter_user.currentData():
            return False
        if self.filter_project.currentData() and item.project_id != self.filter_project.currentData():
            return False
        if self.filter_part.currentData() and item.part_id != self.filter_part.currentData():
            return False
        progress = self.filter_progress.currentData()
        return not ((progress == "NOT_STARTED" and item.completed_quantity != 0)
                    or (progress == "IN_PROGRESS" and not 0 < item.completed_quantity < item.total_quantity)
                    or (progress == "DONE" and item.completed_quantity < item.total_quantity))


def _set_work_row(
    table: QTableWidget, row: int, item: WorkItemView, values: list[str], *,
    progress_column: int, id_column: int,
) -> None:
    for column, value in enumerate(values):
        if column == progress_column:
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(round(item.progress_ratio * 100))
            table.setCellWidget(row, column, bar)
            continue
        cell = QTableWidgetItem(value)
        if column == id_column:
            cell.setData(Qt.ItemDataRole.UserRole, item.work_item_id)
            cell.setData(Qt.ItemDataRole.UserRole + 1, item.assignment_id)
        table.setItem(row, column, cell)


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


def _fill_filter(combo: QComboBox, label: str, values: list[tuple[str, str]], selected: str | None) -> None:
    combo.blockSignals(True)
    combo.clear()
    combo.addItem(label, None)
    for identity, text in values:
        combo.addItem(text, identity)
    index = combo.findData(selected)
    combo.setCurrentIndex(index if index >= 0 else 0)
    combo.blockSignals(False)


def _section(text: str) -> QLabel:
    label = QLabel(text)
    label.setProperty("role", "section")
    return label


def _muted(text: str) -> QLabel:
    label = QLabel(text)
    label.setProperty("role", "muted")
    return label


def _detail_scroll(detail: QWidget) -> QScrollArea:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setMinimumWidth(520)
    scroll.setWidget(detail)
    return scroll
