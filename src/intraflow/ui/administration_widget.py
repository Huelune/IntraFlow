from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout, QHBoxLayout, QLabel, QPushButton, QSplitter, QTabWidget,
    QTableWidget, QTableWidgetItem, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from intraflow.services.administration_service import AdministrationService
from intraflow.services.progress_service import ProgressService
from intraflow.services.work_service import WorkService
from intraflow.ui.dialogs import DeviceDialog, PartDialog, ProjectDialog, UnitDialog, UserDialog
from intraflow.ui.table_view import configure_columns


class AdministrationWidget(QWidget):
    def __init__(
        self, service: AdministrationService, work: WorkService, on_changed: Callable[[], None],
        progress: ProgressService | None = None,
    ) -> None:
        super().__init__()
        self.service, self.work, self.progress, self.on_changed = service, work, progress, on_changed
        self.current_type: str | None = None
        self.current_id: str | None = None
        self.user_current_type: str | None = None
        self.user_current_id: str | None = None
        self.unit_current_id: str | None = None
        self.is_admin, _ = service.current_permissions()
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_hierarchy(), "프로젝트·파트")
        if self.is_admin:
            self.tabs.addTab(self._build_users(), "사용자·기기")
            self.tabs.addTab(self._build_units(), "단위")
        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs)
        self.refresh()

    def _build_hierarchy(self) -> QWidget:
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["프로젝트 / 파트 / 사용자 업무", "소유자", "상태", "기간", "진행률"])
        self.tree.setAlternatingRowColors(True)
        configure_columns(self.tree, "admin-project-hierarchy", (300, 110, 90, 190, 110))
        self.tree.itemSelectionChanged.connect(self._load_hierarchy_detail)
        self.hierarchy_detail = _ReadOnlyDetail()
        self.hierarchy_history = QTableWidget(0, 6)
        self.hierarchy_history.setHorizontalHeaderLabels(["시각", "이전량", "증감량", "현재량", "진행률", "메모"])
        self.hierarchy_history.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        configure_columns(
            self.hierarchy_history, "admin-public-history", (160, 75, 75, 75, 85, 240),
        )
        self.new_project_button, self.new_part_button = QPushButton("새 프로젝트"), QPushButton("새 파트")
        self.new_project_button.setProperty("primary", True)
        self.edit_button, refresh = QPushButton("수정"), QPushButton("새로고침")
        self.new_project_button.setEnabled(self.is_admin)
        self.new_project_button.clicked.connect(self._new_project)
        self.new_part_button.clicked.connect(self._new_part)
        self.edit_button.clicked.connect(self._edit_hierarchy)
        refresh.clicked.connect(self.refresh)
        actions = QHBoxLayout()
        for button in (refresh, self.new_project_button, self.new_part_button, self.edit_button):
            actions.addWidget(button)
        detail_card = QWidget()
        detail_card.setProperty("card", True)
        detail_layout = QVBoxLayout(detail_card)
        detail_layout.setContentsMargins(16, 16, 16, 16)
        detail_layout.addLayout(actions)
        detail_layout.addWidget(self.hierarchy_detail)
        detail_layout.addWidget(_section("공개 진행 이력"))
        detail_layout.addWidget(self.hierarchy_history)
        splitter = QSplitter()
        splitter.addWidget(self.tree)
        splitter.addWidget(detail_card)
        splitter.setSizes([760, 440])
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(splitter)
        return page

    def _build_users(self) -> QWidget:
        self.user_tree = QTreeWidget()
        self.user_tree.setHeaderLabels(["사용자 / 기기", "유형", "상태"])
        self.user_tree.setAlternatingRowColors(True)
        configure_columns(self.user_tree, "admin-users-devices", (240, 120, 100))
        self.user_tree.itemSelectionChanged.connect(self._load_user_detail)
        self.user_detail = _ReadOnlyDetail()
        add_user, add_device, edit, refresh = (
            QPushButton("새 사용자"), QPushButton("새 기기"), QPushButton("수정"), QPushButton("새로고침"))
        add_user.setProperty("primary", True)
        add_user.clicked.connect(self._new_user)
        add_device.clicked.connect(self._new_device)
        edit.clicked.connect(self._edit_user_or_device)
        refresh.clicked.connect(self.refresh)
        self.user_edit_button, self.new_device_button = edit, add_device
        actions = QHBoxLayout()
        for button in (refresh, add_user, add_device, edit):
            actions.addWidget(button)
        detail_card = QWidget()
        detail_card.setProperty("card", True)
        detail_layout = QVBoxLayout(detail_card)
        detail_layout.setContentsMargins(16, 16, 16, 16)
        detail_layout.addLayout(actions)
        detail_layout.addWidget(self.user_detail)
        detail_layout.addStretch()
        splitter = QSplitter()
        splitter.addWidget(self.user_tree)
        splitter.addWidget(detail_card)
        splitter.setSizes([700, 420])
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(splitter)
        return page

    def _build_units(self) -> QWidget:
        self.unit_table = QTableWidget(0, 4)
        self.unit_table.setHorizontalHeaderLabels(["코드", "표시 이름", "정렬", "상태"])
        self.unit_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.unit_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.unit_table.setAlternatingRowColors(True)
        configure_columns(self.unit_table, "admin-units", (110, 200, 90, 110))
        self.unit_table.itemSelectionChanged.connect(self._load_unit_detail)
        self.unit_detail = _ReadOnlyDetail()
        add, edit, refresh = QPushButton("새 단위"), QPushButton("수정"), QPushButton("새로고침")
        add.setProperty("primary", True)
        add.clicked.connect(self._new_unit)
        edit.clicked.connect(self._edit_unit)
        refresh.clicked.connect(self.refresh)
        self.unit_edit_button = edit
        actions = QHBoxLayout()
        for button in (refresh, add, edit):
            actions.addWidget(button)
        detail_card = QWidget()
        detail_card.setProperty("card", True)
        detail_layout = QVBoxLayout(detail_card)
        detail_layout.setContentsMargins(16, 16, 16, 16)
        detail_layout.addLayout(actions)
        detail_layout.addWidget(self.unit_detail)
        detail_layout.addStretch()
        splitter = QSplitter()
        splitter.addWidget(self.unit_table)
        splitter.addWidget(detail_card)
        splitter.setSizes([700, 420])
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(splitter)
        return page

    def refresh(self, *_args, automatic: bool = False) -> None:
        selected = (self.current_type, self.current_id)
        projects, parts = self.service.list_projects(), self.service.list_parts()
        work_items = self.work.list_team_work_items(include_inactive=True)
        self.tree.blockSignals(True)
        self.tree.clear()
        project_nodes: dict[str, QTreeWidgetItem] = {}
        part_nodes: dict[str, QTreeWidgetItem] = {}
        for project in projects:
            node = QTreeWidgetItem([project.name, "", "활성" if project.status == "ACTIVE" else "비활성",
                                    f"{project.planned_start} ~ {project.planned_end}", ""])
            node.setData(0, Qt.ItemDataRole.UserRole, ("project", project.id))
            self.tree.addTopLevelItem(node)
            project_nodes[project.id] = node
        for part in parts:
            parent = project_nodes.get(part.project_id)
            if parent is None:
                continue
            node = QTreeWidgetItem([part.name, "", "활성" if part.is_active else "비활성",
                                    f"{part.planned_start} ~ {part.planned_end}", ""])
            node.setData(0, Qt.ItemDataRole.UserRole, ("part", part.id))
            parent.addChild(node)
            part_nodes[part.id] = node
        for item in work_items:
            parent = part_nodes.get(item.part_id)
            if parent is None:
                continue
            state = "일정 경고" if item.date_warning else ("활성" if item.effective_active else "비활성")
            node = QTreeWidgetItem([item.name, item.owner_name, state,
                                    f"{item.planned_start} ~ {item.planned_end}", f"{item.progress_ratio:.0%}"])
            node.setData(0, Qt.ItemDataRole.UserRole, ("work", item.work_item_id))
            parent.addChild(node)
        self.tree.expandAll()
        node = self._find_node(self.tree, *selected)
        if node is not None:
            self.tree.setCurrentItem(node)
        self.tree.blockSignals(False)
        if node is not None:
            self._load_hierarchy_detail()
        else:
            self.current_type = self.current_id = None
            self.hierarchy_detail.clear()
            self.hierarchy_history.setRowCount(0)
        if self.is_admin:
            self._refresh_users()
            self._refresh_units()

    def _refresh_users(self) -> None:
        selected = (getattr(self, "user_current_type", None), getattr(self, "user_current_id", None))
        users, devices = self.service.list_users(), self.service.list_devices()
        self.user_tree.blockSignals(True)
        self.user_tree.clear()
        nodes = {}
        for user in users:
            node = QTreeWidgetItem([user.display_name, "사용자", "활성" if user.is_active else "비활성"])
            node.setData(0, Qt.ItemDataRole.UserRole, ("user", user.id))
            self.user_tree.addTopLevelItem(node)
            nodes[user.id] = node
        for device in devices:
            parent = nodes.get(device.user_id)
            if parent:
                node = QTreeWidgetItem([device.device_name or "이름 없음", "기기", "현재" if device.is_current else "등록"])
                node.setData(0, Qt.ItemDataRole.UserRole, ("device", device.id))
                parent.addChild(node)
        self.user_tree.expandAll()
        node = self._find_node(self.user_tree, *selected)
        if node:
            self.user_tree.setCurrentItem(node)
        self.user_tree.blockSignals(False)
        if node:
            self._load_user_detail()

    def _refresh_units(self) -> None:
        selected = getattr(self, "unit_current_id", None)
        units = self.service.list_units()
        self.unit_table.blockSignals(True)
        self.unit_table.setRowCount(len(units))
        selected_row = -1
        for row, unit in enumerate(units):
            values = [unit.code, unit.display_name, str(unit.sort_order), "활성" if unit.is_active else "비활성"]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if column == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, unit.id)
                self.unit_table.setItem(row, column, cell)
            if unit.id == selected:
                selected_row = row
        if selected_row >= 0:
            self.unit_table.selectRow(selected_row)
        self.unit_table.blockSignals(False)
        if selected_row >= 0:
            self._load_unit_detail()

    def _load_hierarchy_detail(self) -> None:
        selected = self.tree.selectedItems()
        if not selected:
            return
        kind, identity = selected[0].data(0, Qt.ItemDataRole.UserRole)
        self.current_type, self.current_id = kind, identity
        self.hierarchy_history.setRowCount(0)
        if kind == "project":
            project = next(x for x in self.service.list_projects() if x.id == identity)
            self.hierarchy_detail.show_values(project.name, [
                ("설명", project.description or "설명 없음"), ("기간", f"{project.planned_start} ~ {project.planned_end}"),
                ("상태", "활성" if project.status == "ACTIVE" else "비활성"),
            ])
            manageable = self.service.can_manage_project(project.id)
            self.new_part_button.setEnabled(manageable)
            self.edit_button.setEnabled(manageable)
        elif kind == "part":
            part = next(x for x in self.service.list_parts() if x.id == identity)
            project = next(x for x in self.service.list_projects() if x.id == part.project_id)
            self.hierarchy_detail.show_values(part.name, [
                ("상위 프로젝트", project.name), ("가중치", f"{part.weight:g}"),
                ("기간", f"{part.planned_start} ~ {part.planned_end}"),
                ("상태", "활성" if part.is_active else "비활성"),
            ])
            manageable = self.service.can_manage_project(project.id)
            self.new_part_button.setEnabled(manageable)
            self.edit_button.setEnabled(manageable)
        else:
            item = self.work.get_team_work_item(identity)
            self.hierarchy_detail.show_values(item.name, [
                ("전체 경로", item.path), ("소유자", item.owner_name), ("설명", item.description or "설명 없음"),
                ("기간", f"{item.planned_start} ~ {item.planned_end}"),
                ("완료량 / 목표량", f"{item.completed_quantity:g} / {item.total_quantity:g}"),
                ("진행률", f"{item.progress_ratio:.0%}"), ("최신 메모", item.note or "없음"),
            ])
            self.new_part_button.setEnabled(False)
            self.edit_button.setEnabled(False)
            if self.progress:
                histories = self.progress.list_public_history(item.assignment_id)
                self._fill_history(histories, item.total_quantity)

    def _load_user_detail(self) -> None:
        selected = self.user_tree.selectedItems()
        if not selected:
            return
        kind, identity = selected[0].data(0, Qt.ItemDataRole.UserRole)
        self.user_current_type, self.user_current_id = kind, identity
        if kind == "user":
            user = next(x for x in self.service.list_users() if x.id == identity)
            self.user_detail.show_values(user.display_name, [
                ("사용자 코드", user.user_code), ("시스템 관리자", "예" if user.is_system_admin else "아니요"),
                ("상태", "활성" if user.is_active else "비활성"),
            ])
            self.new_device_button.setEnabled(True)
        else:
            device = next(x for x in self.service.list_devices() if x.id == identity)
            user = next(x for x in self.service.list_users() if x.id == device.user_id)
            self.user_detail.show_values(device.device_name or "이름 없음", [
                ("소유 사용자", user.display_name), ("현재 기기", "예" if device.is_current else "아니요"),
                ("마지막 확인", device.last_seen_at or "기록 없음"),
            ])
            self.new_device_button.setEnabled(False)
        self.user_edit_button.setEnabled(True)

    def _load_unit_detail(self) -> None:
        row = self.unit_table.currentRow()
        cell = self.unit_table.item(row, 0) if row >= 0 else None
        if cell is None:
            return
        self.unit_current_id = cell.data(Qt.ItemDataRole.UserRole)
        unit = next(x for x in self.service.list_units() if x.id == self.unit_current_id)
        self.unit_detail.show_values(unit.display_name, [
            ("코드", unit.code), ("정렬 순서", str(unit.sort_order)),
            ("상태", "활성" if unit.is_active else "비활성"),
        ])
        self.unit_edit_button.setEnabled(True)

    def _new_project(self) -> None:
        self._run_dialog(ProjectDialog(self.service))

    def _new_part(self) -> None:
        project = self._selected_project()
        if project:
            self._run_dialog(PartDialog(self.service, project))

    def _edit_hierarchy(self) -> None:
        if self.current_type == "project":
            project = next(x for x in self.service.list_projects() if x.id == self.current_id)
            self._run_dialog(ProjectDialog(self.service, project))
        elif self.current_type == "part":
            part = next(x for x in self.service.list_parts() if x.id == self.current_id)
            project = next(x for x in self.service.list_projects() if x.id == part.project_id)
            self._run_dialog(PartDialog(self.service, project, part))

    def _new_user(self) -> None:
        self._run_dialog(UserDialog(self.service))

    def _new_device(self) -> None:
        user_id = self.user_current_id if self.user_current_type == "user" else None
        self._run_dialog(DeviceDialog(self.service, user_id=user_id))

    def _edit_user_or_device(self) -> None:
        if self.user_current_type == "user":
            user = next(x for x in self.service.list_users() if x.id == self.user_current_id)
            self._run_dialog(UserDialog(self.service, user))
        elif self.user_current_type == "device":
            device = next(x for x in self.service.list_devices() if x.id == self.user_current_id)
            self._run_dialog(DeviceDialog(self.service, device))

    def _new_unit(self) -> None:
        self._run_dialog(UnitDialog(self.service))

    def _edit_unit(self) -> None:
        unit = next((x for x in self.service.list_units() if x.id == getattr(self, "unit_current_id", None)), None)
        if unit:
            self._run_dialog(UnitDialog(self.service, unit))

    def _run_dialog(self, dialog) -> None:
        if dialog.exec() == dialog.DialogCode.Accepted:
            self.refresh()
            self.on_changed()

    def _selected_project(self):
        if self.current_type == "project":
            return next((x for x in self.service.list_projects() if x.id == self.current_id), None)
        if self.current_type == "part":
            part = next((x for x in self.service.list_parts() if x.id == self.current_id), None)
            return next((x for x in self.service.list_projects() if part and x.id == part.project_id), None)
        return None

    def _fill_history(self, histories, total: float) -> None:
        self.hierarchy_history.setRowCount(len(histories))
        for row, history in enumerate(histories):
            ratio = history.current_quantity / total if total else 0
            values = [history.created_at, f"{history.previous_quantity:g}", f"{history.delta_quantity:g}",
                      f"{history.current_quantity:g}", f"{ratio:.0%}", history.note or ""]
            for column, value in enumerate(values):
                self.hierarchy_history.setItem(row, column, QTableWidgetItem(value))

    @staticmethod
    def _find_node(tree: QTreeWidget, kind: str | None, identity: str | None):
        if not kind or not identity:
            return None
        pending = [tree.topLevelItem(index) for index in range(tree.topLevelItemCount())]
        while pending:
            node = pending.pop()
            if node.data(0, Qt.ItemDataRole.UserRole) == (kind, identity):
                return node
            pending.extend(node.child(index) for index in range(node.childCount()))
        return None


class _ReadOnlyDetail(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.title = QLabel("항목을 선택하세요")
        self.title.setProperty("role", "title")
        self.form = QFormLayout()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.addWidget(self.title)
        layout.addLayout(self.form)

    def clear(self) -> None:
        self.title.setText("항목을 선택하세요")
        while self.form.rowCount():
            self.form.removeRow(0)

    def show_values(self, title: str, values: list[tuple[str, str]]) -> None:
        self.clear()
        self.title.setText(title)
        refreshed_at = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        for label, value in [*values, ("로컬 새로고침", refreshed_at)]:
            widget = QLabel(value)
            widget.setWordWrap(True)
            self.form.addRow(label, widget)


def _section(text: str) -> QLabel:
    label = QLabel(text)
    label.setProperty("role", "section")
    return label
