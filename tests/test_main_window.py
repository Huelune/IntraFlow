from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QApplication, QScrollArea, QToolButton
from sqlalchemy.orm import Session, sessionmaker

from intraflow.services.progress_service import ProgressService
from intraflow.ui.main_window import MainWindow
from intraflow.ui.work_widgets import ProgressCell
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
    detail_scrolls = [x for x in window.my_work.findChildren(QScrollArea) if x.widget() is window.my_work.detail]
    assert len(detail_scrolls) == 1
    assert detail_scrolls[0].minimumWidth() == 520
    assert window.my_work.table.parentWidget().minimumWidth() >= 420
    assert isinstance(window.my_work.detail.refresh_button, QToolButton)
    assert window.my_work.detail.refresh_button.height() <= 28
    assert window.my_work.detail.history.isVisible()
    window.my_work.detail.history_toggle.setChecked(False)
    assert not window.my_work.detail.history.isVisible()
    window.my_work.detail.history_toggle.setChecked(True)
    window.my_work.detail.note.setPlainText("저장하지 않은 메모")
    window.refresh_current_tab(automatic=True)
    assert window.my_work.detail.note.toPlainText() == "저장하지 않은 메모"
    window.settings_widget.enabled.setChecked(True)
    window.settings_widget.interval.setCurrentIndex(window.settings_widget.interval.findData(30))
    window.settings_widget.refresh(automatic=True)
    assert window.settings_widget.enabled.isChecked() is True
    assert window.settings_widget.interval.currentData() == 30
    assert window.settings_widget.timezone.findData("Asia/Seoul") >= 0
    assert window.my_work.table.rowCount() == 1
    assert isinstance(window.my_work.table.cellWidget(0, 6), ProgressCell)
    assert window.my_work.table.columnWidth(6) >= 110
    progress.add_delta(item.assignment_id, 5, "진행")
    window.refresh_all()
    app.processEvents()
    assert window.my_work.table.cellWidget(0, 6).value() == 50
    assert window.team_work.table.rowCount() == 1
    assert window.team_work.detail.history.rowCount() == 1
    window.team_work.view_buttons[1].click()
    window.team_work.calendar.setSelectedDate(QDate(2026, 8, 5))
    window.team_work.refresh(automatic=True)
    assert window.team_work.left_stack.currentIndex() == 1
    assert window.team_work.agenda.rowCount() == 1
    assert window.team_work.calendar.selectedDate() == QDate(2026, 8, 5)
    window.team_work.agenda.selectRow(0)
    assert window.team_work.detail.title.text() == "업무"
    window.team_work.view_buttons[2].click()
    assert window.team_work.left_stack.currentIndex() == 2
    assert window.team_work.overview_tree.topLevelItemCount() == 1
    project_node = window.team_work.overview_tree.topLevelItem(0)
    assert isinstance(window.team_work.overview_tree.itemWidget(project_node, 1), ProgressCell)
    window.team_work.overview_tree.setCurrentItem(project_node)
    assert window.team_work.detail_stack.currentIndex() == 1
    assert window.team_work.aggregate_detail.title.text() == "프로젝트"
    normal_width = window.my_work.table.width()
    window.resize(1440, 900)
    app.processEvents()
    assert window.my_work.table.width() >= normal_width
    window.close()
