from __future__ import annotations

from PySide6.QtWidgets import QMainWindow, QTabWidget

from intraflow.services.administration_service import AdministrationService
from intraflow.services.progress_service import ProgressService
from intraflow.services.work_service import WorkService
from intraflow.sync.sync_service import SyncService
from intraflow.ui.administration_widget import AdministrationWidget
from intraflow.ui.sync_widget import SyncWidget
from intraflow.ui.work_widgets import MyWorkWidget, TeamWorkWidget


class MainWindow(QMainWindow):
    def __init__(
        self, work: WorkService, progress: ProgressService,
        administration: AdministrationService | None = None, sync: SyncService | None = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle("IntraFlow - 업무 관리")
        self.resize(1280, 800)
        self.tabs = QTabWidget()
        self.my_work = MyWorkWidget(work, progress, self.refresh_all)
        self.team_work = TeamWorkWidget(work, self.open_my_work)
        self.tabs.addTab(self.my_work, "내 업무")
        self.tabs.addTab(self.team_work, "팀 업무")
        self.administration_widget = None
        self.sync_widget = None
        if administration is not None:
            is_admin, is_editor = administration.current_permissions()
            if is_admin or is_editor:
                self.administration_widget = AdministrationWidget(administration, work, self.refresh_all)
                self.tabs.addTab(self.administration_widget, "관리")
        if sync is not None:
            self.sync_widget = SyncWidget(sync, self.refresh_all)
            self.tabs.addTab(self.sync_widget, "동기화")
        self.setCentralWidget(self.tabs)

    def open_my_work(self, work_item_id: str) -> None:
        self.tabs.setCurrentWidget(self.my_work)
        self.my_work.select_item(work_item_id)

    def refresh_all(self) -> None:
        self.my_work.refresh()
        self.team_work.refresh()
        if self.administration_widget is not None:
            self.administration_widget.refresh()
        if self.sync_widget is not None:
            self.sync_widget.refresh()
