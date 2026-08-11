from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from intraflow.services.assignment_service import AssignmentService
from intraflow.services.errors import IntraFlowError
from intraflow.services.progress_service import ProgressService


class MainWindow(QMainWindow):
    def __init__(self, assignments: AssignmentService, progress: ProgressService, sync_now: Callable[[], int] | None = None) -> None:
        super().__init__()
        self.assignments = assignments
        self.progress = progress
        self.sync_now = sync_now
        self.setWindowTitle("IntraFlow - 내 업무")
        self.resize(1120, 700)
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(["업무", "프로젝트", "파트", "단위", "완료", "배정", "진행률", "일정"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.quantity = QDoubleSpinBox()
        self.quantity.setRange(-1_000_000, 1_000_000)
        self.quantity.setDecimals(2)
        self.quantity.setSingleStep(1)
        self.note = QLineEdit()
        self.note.setPlaceholderText("선택 메모")
        self.apply_button = QPushButton("진행 반영")
        self.apply_button.clicked.connect(self.apply_progress)
        self.note.returnPressed.connect(self.apply_progress)
        self.sync_label = QLabel()
        self.sync_button = QPushButton("동기화 시도")
        self.sync_button.setEnabled(sync_now is not None)
        self.sync_button.clicked.connect(self.run_sync)
        form = QFormLayout()
        form.addRow("오늘 진행량", self.quantity)
        form.addRow("메모", self.note)
        form.addRow("", self.apply_button)
        status = QHBoxLayout()
        status.addWidget(self.sync_label)
        status.addStretch()
        status.addWidget(self.sync_button)
        layout = QVBoxLayout()
        layout.addWidget(self.table, stretch=1)
        layout.addLayout(form)
        layout.addLayout(status)
        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)
        self.refresh()

    def refresh(self) -> None:
        rows = self.assignments.list_active()
        self.table.setRowCount(len(rows))
        for row_index, item in enumerate(rows):
            values = [item.work_item_name, item.project_name, item.part_name, item.unit_name, f"{item.completed_quantity:g}", f"{item.allocated_quantity:g}", f"{item.progress_ratio:.0%}", " ~ ".join(value for value in [item.schedule_start, item.schedule_end] if value) or "-"]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if column == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, item.assignment_id)
                self.table.setItem(row_index, column, cell)
        self.sync_label.setText(f"동기화 상태: {self.assignments.sync_status()}")
        if rows and self.table.currentRow() < 0:
            self.table.selectRow(0)

    def _selection_changed(self) -> None:
        self.apply_button.setEnabled(self._selected_assignment_id() is not None)

    def _selected_assignment_id(self) -> str | None:
        row = self.table.currentRow()
        item = self.table.item(row, 0) if row >= 0 else None
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def apply_progress(self) -> None:
        assignment_id = self._selected_assignment_id()
        if assignment_id is None:
            QMessageBox.information(self, "업무 선택", "진행량을 반영할 업무를 선택하세요.")
            return
        try:
            self.progress.add_delta(assignment_id, self.quantity.value(), self.note.text() or None)
        except IntraFlowError as exc:
            QMessageBox.warning(self, "진행 반영 실패", str(exc))
            return
        self.quantity.setValue(0)
        self.note.clear()
        self.refresh()

    def run_sync(self) -> None:
        if self.sync_now is None:
            return
        try:
            self.sync_now()
        except IntraFlowError as exc:
            QMessageBox.warning(self, "동기화 실패", f"로컬 작업은 안전하게 저장되어 있습니다.\n{exc}")
        self.refresh()
