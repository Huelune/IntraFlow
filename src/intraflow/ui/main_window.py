from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDoubleSpinBox, QFormLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from intraflow.services.administration_service import AdministrationService
from intraflow.services.assignment_service import AssignmentService
from intraflow.services.errors import IntraFlowError
from intraflow.services.progress_service import ProgressService
from intraflow.sync.sync_service import SyncService
from intraflow.ui.administration_widget import AdministrationWidget
from intraflow.ui.sync_widget import SyncWidget


class MyWorkWidget(QWidget):
    def __init__(self, assignments: AssignmentService, progress: ProgressService) -> None:
        super().__init__()
        self.assignments, self.progress = assignments, progress
        self.empty_message = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(["업무", "프로젝트", "파트", "단위", "완료량", "배정량", "진행률", "일정"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.quantity = QDoubleSpinBox()
        self.quantity.setRange(-1_000_000, 1_000_000)
        self.quantity.setDecimals(2)
        self.note = QLineEdit(placeholderText="선택 메모")
        self.apply_button = QPushButton("진행량 반영")
        self.apply_button.clicked.connect(self.apply_progress)
        self.note.returnPressed.connect(self.apply_progress)
        self.status_label = QLabel()
        form = QFormLayout()
        form.addRow("오늘 진행량", self.quantity)
        form.addRow("메모", self.note)
        form.addRow("", self.apply_button)
        layout = QVBoxLayout(self)
        layout.addWidget(self.empty_message)
        layout.addWidget(self.table, stretch=1)
        layout.addLayout(form)
        layout.addWidget(self.status_label)
        self.refresh()

    def refresh(self) -> None:
        rows = self.assignments.list_active()
        self.table.setRowCount(len(rows))
        for row_index, item in enumerate(rows):
            values = [item.work_item_name, item.project_name, item.part_name, item.unit_name, f"{item.completed_quantity:g}", f"{item.allocated_quantity:g}", f"{item.progress_ratio:.0%}", " ~ ".join(value for value in (item.schedule_start, item.schedule_end) if value) or "-"]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if column == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, item.assignment_id)
                self.table.setItem(row_index, column, cell)
        self.empty_message.setText(self.assignments.empty_state_message() if not rows else "")
        self.empty_message.setVisible(not rows)
        self.apply_button.setEnabled(bool(rows))
        self.status_label.setText(f"동기화 상태: {self.assignments.sync_status()}")
        if rows:
            self.table.selectRow(0)

    def apply_progress(self) -> None:
        row = self.table.currentRow()
        item = self.table.item(row, 0) if row >= 0 else None
        if item is None:
            QMessageBox.information(self, "업무 선택", "진행량을 반영할 업무를 선택하세요.")
            return
        try:
            self.progress.add_delta(item.data(Qt.ItemDataRole.UserRole), self.quantity.value(), self.note.text() or None)
        except IntraFlowError as exc:
            QMessageBox.warning(self, "진행량 반영 실패", str(exc))
            return
        self.quantity.setValue(0)
        self.note.clear()
        self.refresh()


class MainWindow(QMainWindow):
    def __init__(self, assignments: AssignmentService, progress: ProgressService, administration: AdministrationService | None = None, sync: SyncService | None = None) -> None:
        super().__init__()
        self.setWindowTitle("IntraFlow - 업무 관리")
        self.resize(1180, 760)
        self.tabs = QTabWidget()
        self.my_work = MyWorkWidget(assignments, progress)
        self.tabs.addTab(self.my_work, "내 업무")
        self.administration_widget = None
        self.sync_widget = None
        if administration is not None:
            is_admin, is_editor = administration.current_permissions()
            if is_admin or is_editor:
                self.administration_widget = AdministrationWidget(administration, self.refresh_all)
                self.tabs.addTab(self.administration_widget, "관리")
        if sync is not None:
            self.sync_widget = SyncWidget(sync, self.refresh_all)
            self.tabs.addTab(self.sync_widget, "동기화")
        self.setCentralWidget(self.tabs)

    def refresh_all(self) -> None:
        self.my_work.refresh()
        if self.administration_widget is not None:
            self.administration_widget.refresh()
        if self.sync_widget is not None:
            self.sync_widget.refresh()
