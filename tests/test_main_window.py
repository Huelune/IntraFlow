from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from sqlalchemy.orm import Session, sessionmaker

from intraflow.services.administration_service import AdministrationService
from intraflow.services.assignment_service import AssignmentService
from intraflow.services.progress_service import ProgressService
from intraflow.services.setup_service import SetupService
from intraflow.ui.main_window import MainWindow


def test_main_window_exposes_admin_and_refreshes_my_work(session_factory: sessionmaker[Session]) -> None:
    app = QApplication.instance() or QApplication([])
    identity = SetupService(session_factory).provision("owner", "Owner", "OWNER-PC")
    admin = AdministrationService(session_factory, current_user_id=identity.user_id)
    assignments = AssignmentService(session_factory, current_user_id=identity.user_id)
    progress = ProgressService(session_factory, current_user_id=identity.user_id, current_device_id=identity.device_id)
    window = MainWindow(assignments, progress, admin)
    window.resize(900, 600)
    window.show()
    app.processEvents()

    assert [window.tabs.tabText(index) for index in range(window.tabs.count())] == ["내 업무", "관리"]
    assert "등록된 프로젝트가 없습니다" in window.my_work.empty_message.text()

    unit_id = admin.create_unit("EA", "개")
    project_id = admin.create_project("프로젝트")
    part_id = admin.create_part(project_id, "파트", 1.0)
    work_id = admin.create_work_item(part_id, "업무", 1, unit_id, 1.0)
    admin.create_assignment(work_id, identity.user_id, 1)
    window.refresh_all()
    app.processEvents()

    assert window.my_work.table.rowCount() == 1
    assert window.my_work.table.horizontalHeaderItem(0).text() == "업무"
    assert window.my_work.table.width() > 500
    normal_width = window.my_work.table.width()
    window.resize(1440, 900)
    app.processEvents()
    assert window.my_work.table.width() > normal_width
    assert "진행률" == window.my_work.table.horizontalHeaderItem(6).text()
    window.close()
