from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QDoubleSpinBox, QFormLayout, QHBoxLayout,
    QLineEdit, QMessageBox, QPushButton, QSpinBox, QSplitter, QTabWidget,
    QTableWidget, QTableWidgetItem, QTextEdit, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from intraflow.services.administration_service import AdministrationService
from intraflow.services.errors import IntraFlowError, ValidationError
from intraflow.services.work_service import WorkService


class AdministrationWidget(QWidget):
    def __init__(self, service: AdministrationService, work: WorkService, on_changed: Callable[[], None]) -> None:
        super().__init__()
        self.service, self.work, self.on_changed = service, work, on_changed
        self.current_type: str | None = None
        self.current_id: str | None = None
        self.dirty = False
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_hierarchy(), "프로젝트·파트")
        is_admin, _is_editor = service.current_permissions()
        if is_admin:
            self.tabs.addTab(self._build_users(), "사용자·기기")
            self.tabs.addTab(self._build_units(), "단위")
        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs)
        self.refresh()

    def _build_hierarchy(self) -> QWidget:
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["프로젝트 / 파트 / 사용자 업무", "소유자", "상태", "기간", "진행률"])
        self.tree.itemSelectionChanged.connect(self._load_selection)
        self.name = QLineEdit()
        self.description = QTextEdit()
        self.description.setMaximumHeight(90)
        self.weight = QDoubleSpinBox()
        self.weight.setRange(0.001, 1)
        self.weight.setDecimals(3)
        self.weight.setValue(1)
        self.start, self.end = _date_edit(), _date_edit()
        self.editor_user = QComboBox()
        self.name.textEdited.connect(self._mark_dirty)
        self.description.textChanged.connect(self._mark_dirty)
        self.weight.valueChanged.connect(self._mark_dirty)
        self.start.dateChanged.connect(self._mark_dirty)
        self.end.dateChanged.connect(self._mark_dirty)
        new_project, new_part = QPushButton("새 프로젝트"), QPushButton("새 파트")
        save, cancel = QPushButton("저장"), QPushButton("취소")
        toggle, add_editor = QPushButton("활성/비활성"), QPushButton("편집자 추가")
        new_project.clicked.connect(self.new_project)
        new_part.clicked.connect(self.new_part)
        save.clicked.connect(self.save)
        cancel.clicked.connect(self._reload_current)
        toggle.clicked.connect(self.toggle)
        add_editor.clicked.connect(self.add_editor)
        form = QFormLayout()
        form.addRow("이름", self.name)
        form.addRow("설명(프로젝트)", self.description)
        form.addRow("가중치(파트)", self.weight)
        form.addRow("시작일", self.start)
        form.addRow("종료일", self.end)
        actions = QHBoxLayout()
        for button in (new_project, new_part, save, cancel, toggle):
            actions.addWidget(button)
        form.addRow(actions)
        form.addRow("추가 편집자", self.editor_user)
        form.addRow(add_editor)
        detail = QWidget()
        detail.setLayout(form)
        splitter = QSplitter()
        splitter.addWidget(self.tree)
        splitter.addWidget(detail)
        splitter.setSizes([760, 360])
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(splitter)
        return page

    def _build_users(self) -> QWidget:
        self.user_table = QTableWidget(0, 4)
        self.user_table.setHorizontalHeaderLabels(["사용자 코드", "표시 이름", "관리자", "상태"])
        self.user_code, self.user_name = QLineEdit(), QLineEdit()
        self.user_admin = QCheckBox("시스템 관리자")
        self.device_name = QLineEdit()
        add, toggle, device = QPushButton("사용자 추가"), QPushButton("선택 사용자 ON/OFF"), QPushButton("기기 추가")
        add.clicked.connect(lambda: self._act(lambda: self.service.create_user(
            self.user_code.text(), self.user_name.text(), is_system_admin=self.user_admin.isChecked())))
        toggle.clicked.connect(self._toggle_user)
        device.clicked.connect(lambda: self._selected(self.user_table, lambda identity: self.service.create_device(
            identity, self.device_name.text())))
        form = QFormLayout()
        form.addRow("사용자 코드", self.user_code)
        form.addRow("표시 이름", self.user_name)
        form.addRow("권한", self.user_admin)
        row = QHBoxLayout()
        row.addWidget(add)
        row.addWidget(toggle)
        form.addRow(row)
        form.addRow("기기 이름", self.device_name)
        form.addRow(device)
        return _table_page(self.user_table, form)

    def _build_units(self) -> QWidget:
        self.unit_table = QTableWidget(0, 3)
        self.unit_table.setHorizontalHeaderLabels(["코드", "표시 이름", "상태"])
        self.unit_code, self.unit_name = QLineEdit(), QLineEdit()
        self.unit_order = QSpinBox()
        add, toggle = QPushButton("단위 추가"), QPushButton("선택 단위 ON/OFF")
        add.clicked.connect(lambda: self._act(lambda: self.service.create_unit(
            self.unit_code.text(), self.unit_name.text(), sort_order=self.unit_order.value())))
        toggle.clicked.connect(self._toggle_unit)
        form = QFormLayout()
        form.addRow("단위 코드", self.unit_code)
        form.addRow("표시 이름", self.unit_name)
        form.addRow("정렬 순서", self.unit_order)
        row = QHBoxLayout()
        row.addWidget(add)
        row.addWidget(toggle)
        form.addRow(row)
        return _table_page(self.unit_table, form)

    def refresh(self) -> None:
        projects, parts = self.service.list_projects(), self.service.list_parts()
        work_items = self.work.list_team_work_items(include_inactive=True)
        self.tree.clear()
        project_nodes: dict[str, QTreeWidgetItem] = {}
        part_nodes: dict[str, QTreeWidgetItem] = {}
        for project in projects:
            node = QTreeWidgetItem([
                project.name, "", "활성" if project.status == "ACTIVE" else "비활성",
                f"{project.planned_start or '-'} ~ {project.planned_end or '-'}", "",
            ])
            node.setData(0, Qt.ItemDataRole.UserRole, ("project", project.id))
            self.tree.addTopLevelItem(node)
            project_nodes[project.id] = node
        for part in parts:
            parent = project_nodes.get(part.project_id)
            if parent is None:
                continue
            node = QTreeWidgetItem([
                part.name, "", "활성" if part.is_active else "비활성",
                f"{part.planned_start or '-'} ~ {part.planned_end or '-'}", "",
            ])
            node.setData(0, Qt.ItemDataRole.UserRole, ("part", part.id))
            parent.addChild(node)
            part_nodes[part.id] = node
        for item in work_items:
            parent = part_nodes.get(item.part_id)
            if parent is None:
                continue
            node = QTreeWidgetItem([
                item.name, item.owner_name,
                "일정 경고" if item.date_warning else ("활성" if item.effective_active else "비활성"),
                f"{item.planned_start or '-'} ~ {item.planned_end or '-'}", f"{item.progress_ratio:.0%}",
            ])
            node.setData(0, Qt.ItemDataRole.UserRole, ("work", item.work_item_id))
            node.setFlags(node.flags() & ~Qt.ItemFlag.ItemIsEditable)
            parent.addChild(node)
        self.tree.expandAll()
        choices = self.service.choices()
        current_editor = self.editor_user.currentData()
        self.editor_user.clear()
        for choice in choices["users"]:
            self.editor_user.addItem(choice.label, choice.id)
        index = self.editor_user.findData(current_editor)
        if index >= 0:
            self.editor_user.setCurrentIndex(index)
        if hasattr(self, "user_table"):
            users = self.service.list_users()
            _fill(self.user_table, [(x.id, [x.user_code, x.display_name, "예" if x.is_system_admin else "아니오",
                                                   "활성" if x.is_active else "비활성"]) for x in users])
        if hasattr(self, "unit_table"):
            units = self.service.list_units()
            _fill(self.unit_table, [(x.id, [x.code, x.display_name, "활성" if x.is_active else "비활성"]) for x in units])

    def new_project(self) -> None:
        if not self._confirm_discard():
            return
        self.current_type, self.current_id = "new_project", None
        self.name.clear()
        self.description.clear()
        self.weight.setValue(1)
        self.dirty = False

    def new_part(self) -> None:
        if not self._confirm_discard():
            return
        project_id = self._selected_project_id()
        if not project_id:
            QMessageBox.information(self, "프로젝트 선택", "파트를 추가할 프로젝트를 먼저 선택하세요.")
            return
        project = next(x for x in self.service.list_projects() if x.id == project_id)
        self.current_type, self.current_id = "new_part", project_id
        self.name.clear()
        self.description.clear()
        _set_date(self.start, project.planned_start)
        _set_date(self.end, project.planned_end)
        self.dirty = False

    def save(self) -> None:
        try:
            if self.current_type == "new_project":
                self.service.create_project(self.name.text(), _date(self.start), _date(self.end), self.description.toPlainText())
            elif self.current_type == "project" and self.current_id:
                self._save_with_warning(lambda allow: self.service.update_project(
                    self.current_id, self.name.text(), _date(self.start), _date(self.end),
                    self.description.toPlainText(), allow_child_conflicts=allow))
            elif self.current_type == "new_part" and self.current_id:
                self.service.create_part(self.current_id, self.name.text(), self.weight.value(), _date(self.start), _date(self.end))
            elif self.current_type == "part" and self.current_id:
                self._save_with_warning(lambda allow: self.service.update_part(
                    self.current_id, self.name.text(), self.weight.value(), _date(self.start), _date(self.end),
                    allow_child_conflicts=allow))
            else:
                QMessageBox.information(self, "항목 선택", "프로젝트 또는 파트를 선택하세요.")
                return
        except IntraFlowError as exc:
            QMessageBox.warning(self, "저장 실패", str(exc))
            return
        self._changed()

    def toggle(self) -> None:
        if self.current_type == "project" and self.current_id:
            project = next(x for x in self.service.list_projects() if x.id == self.current_id)
            self._act(lambda: self.service.set_project_active(project.id, project.status != "ACTIVE"))
        elif self.current_type == "part" and self.current_id:
            part = next(x for x in self.service.list_parts() if x.id == self.current_id)
            self._act(lambda: self.service.set_part_active(part.id, not bool(part.is_active)))

    def add_editor(self) -> None:
        project_id = self._selected_project_id()
        if project_id:
            self._act(lambda: self.service.add_project_editor(project_id, self.editor_user.currentData()))

    def _load_selection(self) -> None:
        selected = self.tree.selectedItems()
        if not selected:
            return
        kind, identity = selected[0].data(0, Qt.ItemDataRole.UserRole)
        if (kind, identity) != (self.current_type, self.current_id) and not self._confirm_discard():
            self.tree.blockSignals(True)
            previous = self._find_node(self.current_type, self.current_id)
            if previous is not None:
                self.tree.setCurrentItem(previous)
            self.tree.blockSignals(False)
            return
        self.current_type, self.current_id = kind, identity
        if kind == "project":
            value = next(x for x in self.service.list_projects() if x.id == identity)
            self.name.setText(value.name)
            self.description.setPlainText(value.description or "")
            _set_date(self.start, value.planned_start)
            _set_date(self.end, value.planned_end)
        elif kind == "part":
            value = next(x for x in self.service.list_parts() if x.id == identity)
            self.name.setText(value.name)
            self.description.clear()
            self.weight.setValue(value.weight)
            _set_date(self.start, value.planned_start)
            _set_date(self.end, value.planned_end)
        self.dirty = False

    def _reload_current(self) -> None:
        selected = self.tree.selectedItems()
        if selected:
            self._load_selection()
        elif self.current_type in {"new_project", "new_part"}:
            self.current_type = self.current_id = None
            self.name.clear()
            self.description.clear()
        self.dirty = False

    def _mark_dirty(self, *_args) -> None:
        self.dirty = True

    def _confirm_discard(self) -> bool:
        if not self.dirty:
            return True
        return QMessageBox.question(
            self, "저장되지 않은 변경", "저장되지 않은 변경을 버리고 이동할까요?",
        ) == QMessageBox.StandardButton.Yes

    def _find_node(self, kind: str | None, identity: str | None) -> QTreeWidgetItem | None:
        if not kind or not identity:
            return None
        pending = [self.tree.topLevelItem(index) for index in range(self.tree.topLevelItemCount())]
        while pending:
            node = pending.pop()
            if node.data(0, Qt.ItemDataRole.UserRole) == (kind, identity):
                return node
            pending.extend(node.child(index) for index in range(node.childCount()))
        return None

    def _selected_project_id(self) -> str | None:
        if self.current_type in {"project", "new_part"}:
            return self.current_id
        if self.current_type == "part" and self.current_id:
            part = next((x for x in self.service.list_parts() if x.id == self.current_id), None)
            return part.project_id if part else None
        return None

    def _save_with_warning(self, action) -> None:
        try:
            action(False)
        except ValidationError as exc:
            if "벗어나는" not in str(exc):
                raise
            if QMessageBox.question(self, "하위 일정 경고", f"{exc}\n그래도 저장할까요?") != QMessageBox.StandardButton.Yes:
                raise
            action(True)

    def _toggle_user(self) -> None:
        row = self.user_table.currentRow()
        if row < 0:
            return
        identity = self.user_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        active = self.user_table.item(row, 3).text() == "활성"
        self._act(lambda: self.service.set_user_active(identity, not active))

    def _toggle_unit(self) -> None:
        row = self.unit_table.currentRow()
        if row < 0:
            return
        identity = self.unit_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        active = self.unit_table.item(row, 2).text() == "활성"
        self._act(lambda: self.service.set_unit_active(identity, not active))

    def _selected(self, table: QTableWidget, action) -> None:
        row = table.currentRow()
        if row < 0:
            QMessageBox.information(self, "항목 선택", "처리할 항목을 선택하세요.")
            return
        self._act(lambda: action(table.item(row, 0).data(Qt.ItemDataRole.UserRole)))

    def _act(self, action) -> None:
        try:
            action()
        except IntraFlowError as exc:
            QMessageBox.warning(self, "처리 실패", str(exc))
            return
        self._changed()

    def _changed(self) -> None:
        self.dirty = False
        self.refresh()
        self.on_changed()


def _date_edit() -> QDateEdit:
    value = QDateEdit(QDate.currentDate())
    value.setCalendarPopup(True)
    value.setDisplayFormat("yyyy-MM-dd")
    return value


def _date(widget: QDateEdit) -> str:
    return widget.date().toString("yyyy-MM-dd")


def _set_date(widget: QDateEdit, value: str | None) -> None:
    if value:
        widget.setDate(QDate.fromString(value, "yyyy-MM-dd"))


def _table_page(table: QTableWidget, form: QFormLayout) -> QWidget:
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    table.horizontalHeader().setStretchLastSection(True)
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.addWidget(table, stretch=1)
    layout.addLayout(form)
    return page


def _fill(table: QTableWidget, rows: list[tuple[str, list[str]]]) -> None:
    table.setRowCount(len(rows))
    for row, (identity, values) in enumerate(rows):
        for column, value in enumerate(values):
            cell = QTableWidgetItem(value)
            if column == 0:
                cell.setData(Qt.ItemDataRole.UserRole, identity)
            table.setItem(row, column, cell)
