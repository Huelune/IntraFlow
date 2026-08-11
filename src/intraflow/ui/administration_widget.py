from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLineEdit,
    QMessageBox, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QTabWidget,
    QVBoxLayout, QWidget,
)

from intraflow.services.administration_service import AdministrationService
from intraflow.services.errors import IntraFlowError


class AdministrationWidget(QWidget):
    def __init__(self, service: AdministrationService, on_changed: Callable[[], None]) -> None:
        super().__init__()
        self.service = service
        self.on_changed = on_changed
        self.tabs = QTabWidget()
        self.user_table = QTableWidget(0, 4)
        self.unit_table = QTableWidget(0, 3)
        self.project_table = QTableWidget(0, 4)
        self.part_table = QTableWidget(0, 3)
        self.work_table = QTableWidget(0, 4)
        self.assignment_table = QTableWidget(0, 4)
        self._build_users()
        self._build_units()
        self._build_projects()
        self._build_parts()
        self._build_work_items()
        self._build_assignments()
        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs)
        self.refresh()

    def _build_users(self) -> None:
        self.user_table.setHorizontalHeaderLabels(["사용자 코드", "표시 이름", "관리자", "상태"])
        self.user_code, self.user_name = QLineEdit(), QLineEdit()
        self.user_admin = QCheckBox("시스템 관리자")
        add = QPushButton("사용자 추가")
        add.clicked.connect(lambda: self._act(lambda: self.service.create_user(
            self.user_code.text(), self.user_name.text(), is_system_admin=self.user_admin.isChecked())))
        disable = QPushButton("선택 사용자 비활성화")
        disable.clicked.connect(lambda: self._selected_action(self.user_table, lambda value: self.service.set_user_active(value, False)))
        self.device_name = QLineEdit()
        device = QPushButton("선택 사용자에 기기 추가")
        device.clicked.connect(lambda: self._selected_action(self.user_table, lambda value: self.service.create_device(value, self.device_name.text())))
        form = QFormLayout()
        form.addRow("사용자 코드", self.user_code)
        form.addRow("표시 이름", self.user_name)
        form.addRow("권한", self.user_admin)
        form.addRow(add, disable)
        form.addRow("기기 이름", self.device_name)
        form.addRow(device)
        self.tabs.addTab(self._page(self.user_table, form), "사용자·기기")

    def _build_units(self) -> None:
        self.unit_table.setHorizontalHeaderLabels(["코드", "표시 이름", "상태"])
        self.unit_code, self.unit_name = QLineEdit(), QLineEdit()
        self.unit_order = QSpinBox()
        add = QPushButton("단위 추가")
        add.clicked.connect(lambda: self._act(lambda: self.service.create_unit(
            self.unit_code.text(), self.unit_name.text(), sort_order=self.unit_order.value())))
        disable = QPushButton("선택 단위 비활성화")
        disable.clicked.connect(lambda: self._selected_action(self.unit_table, lambda value: self.service.set_unit_active(value, False)))
        form = QFormLayout()
        form.addRow("단위 코드", self.unit_code)
        form.addRow("표시 이름", self.unit_name)
        form.addRow("정렬 순서", self.unit_order)
        form.addRow(add, disable)
        self.tabs.addTab(self._page(self.unit_table, form), "단위")

    def _build_projects(self) -> None:
        self.project_table.setHorizontalHeaderLabels(["프로젝트", "상태", "시작일", "종료일"])
        self.project_name = QLineEdit()
        self.project_start, self.project_end = self._date_inputs()
        add = QPushButton("프로젝트 추가")
        add.clicked.connect(lambda: self._act(lambda: self.service.create_project(
            self.project_name.text(), self.project_start.text() or None, self.project_end.text() or None)))
        update = QPushButton("선택 프로젝트 수정")
        update.clicked.connect(lambda: self._selected_action(self.project_table, lambda value: self.service.update_project(
            value, self.project_name.text(), self.project_start.text() or None, self.project_end.text() or None)))
        self.editor_user = QComboBox()
        editor = QPushButton("선택 프로젝트에 편집자 추가")
        editor.clicked.connect(lambda: self._selected_action(
            self.project_table, lambda project_id: self.service.add_project_editor(project_id, self.editor_user.currentData())))
        form = QFormLayout()
        form.addRow("프로젝트명", self.project_name)
        form.addRow("시작일", self.project_start)
        form.addRow("종료일", self.project_end)
        form.addRow(add, update)
        form.addRow("추가 편집자", self.editor_user)
        form.addRow(editor)
        self.tabs.addTab(self._page(self.project_table, form), "프로젝트")

    def _build_parts(self) -> None:
        self.part_table.setHorizontalHeaderLabels(["프로젝트", "파트", "가중치"])
        self.part_project, self.part_name = QComboBox(), QLineEdit()
        self.part_weight = self._quantity(1.0, 1.0)
        self.part_start, self.part_end = self._date_inputs()
        add = QPushButton("파트 추가")
        add.clicked.connect(lambda: self._act(lambda: self.service.create_part(
            self.part_project.currentData(), self.part_name.text(), self.part_weight.value(),
            self.part_start.text() or None, self.part_end.text() or None)))
        update = QPushButton("선택 파트 수정")
        update.clicked.connect(lambda: self._selected_action(self.part_table, lambda value: self.service.update_part(
            value, self.part_name.text(), self.part_weight.value(), self.part_start.text() or None, self.part_end.text() or None)))
        form = QFormLayout()
        form.addRow("프로젝트", self.part_project)
        form.addRow("파트명", self.part_name)
        form.addRow("가중치", self.part_weight)
        form.addRow("시작일", self.part_start)
        form.addRow("종료일", self.part_end)
        form.addRow(add, update)
        self.tabs.addTab(self._page(self.part_table, form), "파트")

    def _build_work_items(self) -> None:
        self.work_table.setHorizontalHeaderLabels(["파트", "업무", "총 수량", "단위"])
        self.work_part, self.work_unit, self.work_name = QComboBox(), QComboBox(), QLineEdit()
        self.work_total = self._quantity(1_000_000, 1)
        self.work_weight = self._quantity(1.0, 1.0)
        self.work_start, self.work_end = self._date_inputs()
        add = QPushButton("업무 추가")
        add.clicked.connect(lambda: self._act(lambda: self.service.create_work_item(
            self.work_part.currentData(), self.work_name.text(), self.work_total.value(),
            self.work_unit.currentData(), self.work_weight.value(),
            self.work_start.text() or None, self.work_end.text() or None)))
        update = QPushButton("선택 업무 수정")
        update.clicked.connect(lambda: self._selected_action(self.work_table, lambda value: self.service.update_work_item(
            value, self.work_name.text(), self.work_total.value(), self.work_unit.currentData(), self.work_weight.value(),
            self.work_start.text() or None, self.work_end.text() or None)))
        form = QFormLayout()
        form.addRow("파트", self.work_part)
        form.addRow("업무명", self.work_name)
        form.addRow("총 수량", self.work_total)
        form.addRow("단위", self.work_unit)
        form.addRow("가중치", self.work_weight)
        form.addRow("시작일", self.work_start)
        form.addRow("종료일", self.work_end)
        form.addRow(add, update)
        self.tabs.addTab(self._page(self.work_table, form), "업무")

    def _build_assignments(self) -> None:
        self.assignment_table.setHorizontalHeaderLabels(["업무", "사용자", "배정량", "상태"])
        self.assignment_work, self.assignment_user = QComboBox(), QComboBox()
        self.assignment_quantity = self._quantity(1_000_000, 1)
        add = QPushButton("업무 배정")
        add.clicked.connect(lambda: self._act(lambda: self.service.create_assignment(
            self.assignment_work.currentData(), self.assignment_user.currentData(), self.assignment_quantity.value())))
        update = QPushButton("선택 배정량 수정")
        update.clicked.connect(lambda: self._selected_action(self.assignment_table, lambda value: self.service.update_assignment_quantity(
            value, self.assignment_quantity.value())))
        cancel = QPushButton("선택 배정 취소")
        cancel.clicked.connect(lambda: self._selected_action(self.assignment_table, self.service.cancel_assignment))
        form = QFormLayout()
        form.addRow("업무", self.assignment_work)
        form.addRow("사용자", self.assignment_user)
        form.addRow("배정 수량", self.assignment_quantity)
        actions = QHBoxLayout()
        actions.addWidget(add)
        actions.addWidget(update)
        actions.addWidget(cancel)
        form.addRow(actions)
        self.tabs.addTab(self._page(self.assignment_table, form), "배정")

    def refresh(self) -> None:
        users, units, projects = self.service.list_users(), self.service.list_units(), self.service.list_projects()
        parts, work_items, assignments = self.service.list_parts(), self.service.list_work_items(), self.service.list_assignments()
        choices = self.service.choices()
        self._fill(self.user_table, [(x.id, [x.user_code, x.display_name, "예" if x.is_system_admin else "아니오", "활성" if x.is_active else "비활성"]) for x in users])
        self._fill(self.unit_table, [(x.id, [x.code, x.display_name, "활성" if x.is_active else "비활성"]) for x in units])
        self._fill(self.project_table, [(x.id, [x.name, x.status, x.planned_start or "-", x.planned_end or "-"]) for x in projects])
        project_names = {x.id: x.name for x in projects}
        self._fill(self.part_table, [(x.id, [project_names.get(x.project_id, "-"), x.name, f"{x.weight:g}"]) for x in parts])
        part_names, unit_names = {x.id: x.name for x in parts}, {x.id: x.display_name for x in units}
        self._fill(self.work_table, [(x.id, [part_names.get(x.part_id, "-"), x.name, f"{x.total_quantity:g}", unit_names.get(x.unit_id, "-")]) for x in work_items])
        work_names, user_names = {x.id: x.name for x in work_items}, {x.id: x.display_name for x in users}
        self._fill(self.assignment_table, [(x.id, [work_names.get(x.work_item_id, "-"), user_names.get(x.user_id, "-"), f"{x.allocated_quantity:g}", x.status]) for x in assignments])
        for combo, key in [(self.editor_user, "users"), (self.part_project, "projects"), (self.work_part, "parts"), (self.work_unit, "units"), (self.assignment_work, "work_items"), (self.assignment_user, "users")]:
            current = combo.currentData()
            combo.clear()
            for choice in choices[key]:
                combo.addItem(choice.label, choice.id)
            index = combo.findData(current)
            if index >= 0:
                combo.setCurrentIndex(index)

    def _act(self, action: Callable[[], object]) -> None:
        try:
            action()
        except IntraFlowError as exc:
            QMessageBox.warning(self, "입력 실패", str(exc))
            return
        self.refresh()
        self.on_changed()

    def _selected_action(self, table: QTableWidget, action: Callable[[str], object]) -> None:
        row = table.currentRow()
        if row < 0 or table.item(row, 0) is None:
            QMessageBox.information(self, "항목 선택", "처리할 항목을 먼저 선택하세요.")
            return
        self._act(lambda: action(table.item(row, 0).data(Qt.ItemDataRole.UserRole)))

    @staticmethod
    def _page(table: QTableWidget, form: QFormLayout) -> QWidget:
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.horizontalHeader().setStretchLastSection(True)
        page, layout = QWidget(), QVBoxLayout()
        layout.addWidget(table, stretch=1)
        layout.addLayout(form)
        page.setLayout(layout)
        return page

    @staticmethod
    def _fill(table: QTableWidget, rows: list[tuple[str, list[str]]]) -> None:
        table.setRowCount(len(rows))
        for row, (identity, values) in enumerate(rows):
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if column == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, identity)
                table.setItem(row, column, cell)

    @staticmethod
    def _quantity(maximum: float, default: float) -> QDoubleSpinBox:
        value = QDoubleSpinBox()
        value.setRange(0, maximum)
        value.setDecimals(3)
        value.setValue(default)
        return value

    @staticmethod
    def _date_inputs() -> tuple[QLineEdit, QLineEdit]:
        start, end = QLineEdit(), QLineEdit()
        start.setPlaceholderText("YYYY-MM-DD")
        end.setPlaceholderText("YYYY-MM-DD")
        return start, end
