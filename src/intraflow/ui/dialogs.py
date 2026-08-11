from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QDialog, QDoubleSpinBox, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox,
    QTextEdit, QVBoxLayout,
)

from intraflow.models import Device, Part, Project, Unit, User
from intraflow.services.administration_service import AdministrationService
from intraflow.services.errors import IntraFlowError, ValidationError
from intraflow.services.work_service import WorkItemView, WorkService


def _date_edit(value: str | None = None) -> QDateEdit:
    widget = QDateEdit(QDate.currentDate())
    widget.setCalendarPopup(True)
    widget.setDisplayFormat("yyyy-MM-dd")
    if value:
        widget.setDate(QDate.fromString(value, "yyyy-MM-dd"))
    return widget


class _BaseDialog(QDialog):
    def __init__(self, title: str, save_text: str) -> None:
        super().__init__()
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(460)
        self.form = QFormLayout()
        self.error = QLabel()
        self.error.setProperty("status", "error")
        self.error.setWordWrap(True)
        self.save_button = QPushButton(save_text)
        self.save_button.setProperty("primary", True)
        cancel = QPushButton("취소")
        cancel.clicked.connect(self.reject)
        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(cancel)
        actions.addWidget(self.save_button)
        layout = QVBoxLayout(self)
        layout.addLayout(self.form)
        layout.addWidget(self.error)
        layout.addLayout(actions)

    def _submit(self, action: Callable[[], object]) -> None:
        self.error.clear()
        try:
            action()
        except (IntraFlowError, ValueError) as exc:
            self.error.setText(str(exc))
        else:
            self.accept()


class WorkItemDialog(_BaseDialog):
    def __init__(self, service: WorkService, item: WorkItemView | None = None) -> None:
        super().__init__("업무 수정" if item else "새 업무", "변경 저장" if item else "추가")
        self.service, self.item = service, item
        self.project, self.part, self.unit = QComboBox(), QComboBox(), QComboBox()
        self.name, self.description = QLineEdit(), QTextEdit()
        self.description.setMaximumHeight(90)
        self.quantity, self.weight = QDoubleSpinBox(), QDoubleSpinBox()
        self.quantity.setRange(0, 1_000_000)
        self.quantity.setDecimals(3)
        self.weight.setRange(0.001, 1)
        self.weight.setDecimals(3)
        self.weight.setValue(1)
        self.start = _date_edit(item.planned_start if item else None)
        self.end = _date_edit(item.planned_end if item else None)
        self.active = QCheckBox("활성")
        self.active.setChecked(item.is_active if item else True)
        projects = service.active_projects()
        if item and not any(identity == item.project_id for identity, _ in projects):
            projects.append((item.project_id, item.project_name))
        for identity, label in projects:
            self.project.addItem(label, identity)
        units = service.active_units()
        if item and not any(identity == item.unit_id for identity, _ in units):
            units.append((item.unit_id, item.unit_name))
        for identity, label in units:
            self.unit.addItem(label, identity)
        self.project.currentIndexChanged.connect(self._fill_parts)
        self.part.currentIndexChanged.connect(self._inherit_part_dates)
        self._fill_parts()
        if item:
            self.name.setText(item.name)
            self.description.setPlainText(item.description or "")
            self.quantity.setValue(item.total_quantity)
            self.weight.setValue(item.weight)
            _select(self.project, item.project_id)
            self._fill_parts()
            part_index = next(
                (i for i in range(self.part.count()) if self.part.itemData(i)[0] == item.part_id), -1)
            if part_index >= 0:
                self.part.setCurrentIndex(part_index)
            _select(self.unit, item.unit_id)
        elif self.part.currentData():
            self._inherit_part_dates()
        self.form.addRow("프로젝트", self.project)
        self.form.addRow("파트", self.part)
        self.form.addRow("업무명", self.name)
        self.form.addRow("설명", self.description)
        self.form.addRow("단위", self.unit)
        self.form.addRow("목표량", self.quantity)
        self.form.addRow("가중치", self.weight)
        self.form.addRow("시작일", self.start)
        self.form.addRow("종료일", self.end)
        self.form.addRow("상태", self.active)
        self.save_button.clicked.connect(self._save)

    def _fill_parts(self) -> None:
        current_data = self.part.currentData()
        selected = current_data[0] if current_data else None
        self.part.clear()
        project_id = self.project.currentData()
        parts = self.service.parts_for_project(project_id) if project_id else []
        if self.item and self.item.project_id == project_id and not any(x[0] == self.item.part_id for x in parts):
            parts.append((self.item.part_id, self.item.part_name, self.item.planned_start, self.item.planned_end))
        for identity, label, start, end in parts:
            self.part.addItem(label, (identity, start, end))
        index = next((i for i in range(self.part.count()) if self.part.itemData(i)[0] == selected), -1)
        if index >= 0:
            self.part.setCurrentIndex(index)

    def _inherit_part_dates(self, *_args) -> None:
        data = self.part.currentData()
        if data and not self.item:
            self.start.setDate(QDate.fromString(data[1], "yyyy-MM-dd"))
            self.end.setDate(QDate.fromString(data[2], "yyyy-MM-dd"))

    def _save(self) -> None:
        part_data = self.part.currentData()
        part_id = part_data[0] if part_data else None
        values = (
            self.name.text(), self.description.toPlainText(), self.quantity.value(),
            self.unit.currentData(), self.weight.value(), self.start.date().toString("yyyy-MM-dd"),
            self.end.date().toString("yyyy-MM-dd"),
        )
        if self.item:
            self._submit(lambda: self.service.update_my_work_item(
                self.item.work_item_id, *values, is_active=self.active.isChecked(), part_id=part_id,
            ))
        else:
            self._submit(lambda: self.service.create_my_work_item(
                part_id, *values, is_active=self.active.isChecked(),
            ))


class ProjectDialog(_BaseDialog):
    def __init__(self, service: AdministrationService, project: Project | None = None) -> None:
        super().__init__("프로젝트 수정" if project else "새 프로젝트", "변경 저장" if project else "추가")
        self.service, self.project = service, project
        self.name, self.description = QLineEdit(), QTextEdit()
        self.description.setMaximumHeight(90)
        self.start = _date_edit(project.planned_start if project else None)
        self.end = _date_edit(project.planned_end if project else None)
        self.active = QCheckBox("활성")
        self.active.setChecked(project.status == "ACTIVE" if project else True)
        self.editor = QComboBox()
        self.editor.addItem("추가하지 않음", None)
        for choice in service.choices()["users"]:
            self.editor.addItem(choice.label, choice.id)
        if project:
            self.name.setText(project.name)
            self.description.setPlainText(project.description or "")
        for label, widget in (("이름", self.name), ("설명", self.description), ("시작일", self.start),
                              ("종료일", self.end), ("상태", self.active), ("편집자 추가", self.editor)):
            self.form.addRow(label, widget)
        self.save_button.clicked.connect(self._save)

    def _save(self) -> None:
        values = (self.name.text(), self.start.date().toString("yyyy-MM-dd"),
                  self.end.date().toString("yyyy-MM-dd"), self.description.toPlainText())
        if not self.project:
            self._submit(lambda: self.service.create_project(
                *values, is_active=self.active.isChecked(), editor_user_id=self.editor.currentData()))
            return
        def save(allow: bool) -> None:
            self.service.update_project(
                self.project.id, *values, allow_child_conflicts=allow,
                is_active=self.active.isChecked(), editor_user_id=self.editor.currentData())
        self._submit(lambda: _save_with_conflict(self, save))


class PartDialog(_BaseDialog):
    def __init__(
        self, service: AdministrationService, project: Project, part: Part | None = None,
    ) -> None:
        super().__init__("파트 수정" if part else "새 파트", "변경 저장" if part else "추가")
        self.service, self.project, self.part = service, project, part
        self.name, self.weight = QLineEdit(), QDoubleSpinBox()
        self.weight.setRange(0.001, 1)
        self.weight.setDecimals(3)
        self.weight.setValue(part.weight if part else 1)
        self.start = _date_edit(part.planned_start if part else project.planned_start)
        self.end = _date_edit(part.planned_end if part else project.planned_end)
        self.active = QCheckBox("활성")
        self.active.setChecked(bool(part.is_active) if part else True)
        if part:
            self.name.setText(part.name)
        self.form.addRow("상위 프로젝트", QLabel(project.name))
        for label, widget in (("이름", self.name), ("가중치", self.weight), ("시작일", self.start),
                              ("종료일", self.end), ("상태", self.active)):
            self.form.addRow(label, widget)
        self.save_button.clicked.connect(self._save)

    def _save(self) -> None:
        values = (self.name.text(), self.weight.value(), self.start.date().toString("yyyy-MM-dd"),
                  self.end.date().toString("yyyy-MM-dd"))
        if not self.part:
            self._submit(lambda: self.service.create_part(
                self.project.id, *values, is_active=self.active.isChecked()))
            return
        def save(allow: bool) -> None:
            self.service.update_part(
                self.part.id, *values, allow_child_conflicts=allow, is_active=self.active.isChecked())
        self._submit(lambda: _save_with_conflict(self, save))


class UserDialog(_BaseDialog):
    def __init__(self, service: AdministrationService, user: User | None = None) -> None:
        super().__init__("사용자 수정" if user else "새 사용자", "변경 저장" if user else "추가")
        self.service, self.user = service, user
        self.code, self.name = QLineEdit(), QLineEdit()
        self.admin, self.active = QCheckBox("시스템 관리자"), QCheckBox("활성")
        self.active.setChecked(bool(user.is_active) if user else True)
        if user:
            self.code.setText(user.user_code)
            self.name.setText(user.display_name)
            self.admin.setChecked(bool(user.is_system_admin))
        for label, widget in (("사용자 코드", self.code), ("표시 이름", self.name),
                              ("권한", self.admin), ("상태", self.active)):
            self.form.addRow(label, widget)
        self.save_button.clicked.connect(self._save)

    def _save(self) -> None:
        if self.user:
            self._submit(lambda: self.service.update_user(
                self.user.id, self.code.text(), self.name.text(), is_system_admin=self.admin.isChecked(),
                is_active=self.active.isChecked()))
        else:
            self._submit(lambda: self.service.create_user(
                self.code.text(), self.name.text(), is_system_admin=self.admin.isChecked(),
                is_active=self.active.isChecked()))


class DeviceDialog(_BaseDialog):
    def __init__(self, service: AdministrationService, device: Device | None = None, user_id: str | None = None) -> None:
        super().__init__("기기 수정" if device else "새 기기", "변경 저장" if device else "추가")
        self.service, self.device = service, device
        self.user, self.name = QComboBox(), QLineEdit()
        for choice in service.choices()["users"]:
            self.user.addItem(choice.label, choice.id)
        _select(self.user, device.user_id if device else user_id)
        self.user.setEnabled(device is None)
        self.current = QCheckBox("현재 기기")
        if device:
            self.name.setText(device.device_name or "")
            self.current.setChecked(bool(device.is_current))
        self.form.addRow("사용자", self.user)
        self.form.addRow("기기 이름", self.name)
        self.form.addRow("상태", self.current)
        self.save_button.clicked.connect(self._save)

    def _save(self) -> None:
        if self.device:
            self._submit(lambda: self.service.update_device(
                self.device.id, self.name.text(), is_current=self.current.isChecked()))
        else:
            self._submit(lambda: self.service.create_device(
                self.user.currentData(), self.name.text(), is_current=self.current.isChecked()))


class UnitDialog(_BaseDialog):
    def __init__(self, service: AdministrationService, unit: Unit | None = None) -> None:
        super().__init__("단위 수정" if unit else "새 단위", "변경 저장" if unit else "추가")
        self.service, self.unit = service, unit
        self.code, self.name, self.order = QLineEdit(), QLineEdit(), QSpinBox()
        self.active = QCheckBox("활성")
        self.active.setChecked(bool(unit.is_active) if unit else True)
        if unit:
            self.code.setText(unit.code)
            self.name.setText(unit.display_name)
            self.order.setValue(unit.sort_order)
        for label, widget in (("코드", self.code), ("표시 이름", self.name),
                              ("정렬 순서", self.order), ("상태", self.active)):
            self.form.addRow(label, widget)
        self.save_button.clicked.connect(self._save)

    def _save(self) -> None:
        if self.unit:
            self._submit(lambda: self.service.update_unit(
                self.unit.id, self.code.text(), self.name.text(), sort_order=self.order.value(),
                is_active=self.active.isChecked()))
        else:
            self._submit(lambda: self.service.create_unit(
                self.code.text(), self.name.text(), sort_order=self.order.value(),
                is_active=self.active.isChecked()))


def _select(combo: QComboBox, identity: str | None) -> None:
    index = combo.findData(identity)
    if index >= 0:
        combo.setCurrentIndex(index)


def _save_with_conflict(parent: QDialog, action: Callable[[bool], None]) -> None:
    try:
        action(False)
    except ValidationError as exc:
        if "벗어나는" not in str(exc):
            raise
        answer = QMessageBox.question(parent, "하위 일정 경고", f"{exc}\n그래도 저장할까요?")
        if answer != QMessageBox.StandardButton.Yes:
            raise
        action(True)
