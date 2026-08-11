from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QProgressBar
from sqlalchemy.orm import Session, sessionmaker

from intraflow.services.progress_service import ProgressService
from intraflow.ui.main_window import MainWindow
from workflow import build_workflow


def test_main_window_exposes_my_team_and_admin_workflows(session_factory: sessionmaker[Session]) -> None:
    app = QApplication.instance() or QApplication([])
    identity, admin, work, _project, _part, item = build_workflow(session_factory)
    progress = ProgressService(session_factory, current_user_id=identity.user_id, current_device_id=identity.device_id)
    window = MainWindow(work, progress, admin)
    window.resize(1000, 650)
    window.show()
    app.processEvents()
    assert [window.tabs.tabText(i) for i in range(window.tabs.count())] == [
        "내 업무", "팀 업무", "관리", "개인 설정",
    ]
    assert window.local_refresh_timer.interval() == 5_000
    assert window.my_work.detail.title.text() == "업무"
    window.my_work.detail.note.setPlainText("저장하지 않은 메모")
    window.refresh_current_tab(automatic=True)
    assert window.my_work.detail.note.toPlainText() == "저장하지 않은 메모"
    window.settings_widget.enabled.setChecked(True)
    window.settings_widget.interval.setCurrentIndex(window.settings_widget.interval.findData(30))
    window.settings_widget.refresh(automatic=True)
    assert window.settings_widget.enabled.isChecked() is True
    assert window.settings_widget.interval.currentData() == 30
    assert window.my_work.table.rowCount() == 1
    assert isinstance(window.my_work.table.cellWidget(0, 6), QProgressBar)
    progress.add_delta(item.assignment_id, 5, "진행")
    window.refresh_all()
    app.processEvents()
    assert window.my_work.table.cellWidget(0, 6).value() == 50
    assert window.team_work.table.rowCount() == 1
    assert window.team_work.detail.history.rowCount() == 1
    normal_width = window.my_work.table.width()
    window.resize(1440, 900)
    app.processEvents()
    assert window.my_work.table.width() >= normal_width
    window.close()
