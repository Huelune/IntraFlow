from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMainWindow, QTabWidget, QVBoxLayout, QWidget

from intraflow.config import AppSettings, RuntimeConfig, settings as default_settings
from intraflow.services.administration_service import AdministrationService
from intraflow.services.progress_service import ProgressService
from intraflow.services.team_view_service import TeamViewService
from intraflow.services.work_service import WorkService
from intraflow.sync.sync_service import SyncService
from intraflow.ui.administration_widget import AdministrationWidget
from intraflow.ui.settings_widget import PersonalSettingsWidget
from intraflow.ui.sync_controller import SyncController
from intraflow.ui.sync_widget import SyncWidget
from intraflow.ui.work_widgets import MyWorkWidget, TeamWorkWidget


class MainWindow(QMainWindow):
    def __init__(
        self, work: WorkService, progress: ProgressService,
        administration: AdministrationService | None = None, sync: SyncService | None = None,
        *, app_settings: AppSettings | None = None, runtime: RuntimeConfig | None = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle("IntraFlow - 업무 관리")
        self.resize(1360, 860)
        app_settings = app_settings or default_settings
        runtime = runtime or RuntimeConfig(
            work.current_user_id, getattr(progress, "current_device_id", None), None,
        )
        self.sync_controller = SyncController(sync, app_settings, runtime)
        self.sync_controller.succeeded.connect(lambda *_args: self.refresh_all())
        self.tabs = QTabWidget()
        self.my_work = MyWorkWidget(work, progress, self.refresh_all)
        team_view = TeamViewService(work.session_factory, current_user_id=work.current_user_id)
        self.team_work = TeamWorkWidget(work, progress, team_view, self.open_my_work)
        self.tabs.addTab(self.my_work, "내 업무")
        self.tabs.addTab(self.team_work, "팀 업무")
        self.administration_widget = None
        if administration is not None:
            is_admin, is_editor = administration.current_permissions()
            if is_admin or is_editor:
                self.administration_widget = AdministrationWidget(
                    administration, work, self.refresh_all, progress=progress)
                self.tabs.addTab(self.administration_widget, "관리")
        self.settings_widget = PersonalSettingsWidget(self.sync_controller)
        self.tabs.addTab(self.settings_widget, "개인 설정")
        self.sync_widget = None
        if sync is not None:
            self.sync_widget = SyncWidget(self.sync_controller, self.refresh_all)
            self.tabs.addTab(self.sync_widget, "동기화")
        self.tabs.currentChanged.connect(self.refresh_current_tab)
        root = QWidget()
        root.setObjectName("appRoot")
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(16, 12, 16, 16)
        root_layout.setSpacing(8)
        root_layout.addLayout(self._build_header(work.current_user_name()))
        root_layout.addWidget(self.tabs)
        self.setCentralWidget(root)
        self.local_refresh_timer = QTimer(self)
        self.local_refresh_timer.setInterval(5_000)
        self.local_refresh_timer.timeout.connect(lambda: self.refresh_current_tab(automatic=True))
        self.local_refresh_timer.start()
        self.sync_controller.status_changed.connect(self._refresh_header)
        self.sync_controller.runtime_changed.connect(lambda _runtime: self._refresh_header())
        self._refresh_header()

    def _build_header(self, user_name: str) -> QHBoxLayout:
        title = QLabel("IntraFlow")
        title.setProperty("role", "title")
        self.user_label = QLabel(f"사용자  {user_name}")
        self.user_label.setProperty("role", "muted")
        self.auto_pull_label, self.sync_status_label = QLabel(), QLabel()
        header = QHBoxLayout()
        header.addWidget(title)
        header.addSpacing(16)
        header.addWidget(self.user_label)
        header.addStretch()
        header.addWidget(self.auto_pull_label)
        header.addSpacing(12)
        header.addWidget(self.sync_status_label)
        return header

    def _refresh_header(self) -> None:
        runtime = self.sync_controller.runtime
        auto = f"자동 Pull {runtime.auto_pull_interval_minutes}분" if runtime.auto_pull_enabled else "자동 Pull 꺼짐"
        self.auto_pull_label.setText(auto)
        self.auto_pull_label.setProperty("status", "active" if runtime.auto_pull_enabled else "")
        self.sync_status_label.setText(self.sync_controller.status_text)
        self.sync_status_label.setProperty("status", "error" if self.sync_controller.last_error else "active")
        for label in (self.auto_pull_label, self.sync_status_label):
            label.style().unpolish(label)
            label.style().polish(label)

    def open_my_work(self, work_item_id: str) -> None:
        self.tabs.setCurrentWidget(self.my_work)
        self.my_work.select_item(work_item_id)

    def refresh_current_tab(self, _index: int | None = None, *, automatic: bool = False) -> None:
        current = self.tabs.currentWidget()
        if current is self.my_work:
            self.my_work.refresh(automatic=automatic)
        elif current is self.team_work:
            self.team_work.refresh(automatic=automatic)
        elif current is self.administration_widget:
            self.administration_widget.refresh(automatic=automatic)
        elif current is self.settings_widget:
            self.settings_widget.refresh(automatic=automatic)
        elif current is self.sync_widget:
            self.sync_widget.refresh(automatic=automatic)

    def refresh_all(self) -> None:
        self.my_work.refresh()
        self.team_work.refresh()
        if self.administration_widget is not None:
            self.administration_widget.refresh()
        self.settings_widget.refresh()
        if self.sync_widget is not None:
            self.sync_widget.refresh()
