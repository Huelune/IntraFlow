from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from sqlalchemy.orm import Session, sessionmaker

from intraflow.services.administration_service import AdministrationService
from intraflow.services.setup_service import SetupService
from intraflow.ui.administration_widget import AdministrationWidget


def test_work_item_unit_selection_guides_empty_state_and_refreshes(
    session_factory: sessionmaker[Session],
) -> None:
    app = QApplication.instance() or QApplication([])
    identity = SetupService(session_factory).provision("owner", "Owner", "OWNER-PC")
    service = AdministrationService(session_factory, current_user_id=identity.user_id)
    widget = AdministrationWidget(service, lambda: None)

    assert widget.work_unit.currentText() == "등록된 단위가 없습니다"
    assert not widget.work_unit.isEnabled()
    assert not widget.work_add_button.isEnabled()
    assert not widget.work_unit_hint.isHidden()
    widget.work_manage_units_button.click()
    assert widget.tabs.currentIndex() == widget.unit_tab_index

    unit_id = service.create_unit("EA", "개")
    widget.refresh()
    app.processEvents()

    assert widget.work_unit.isEnabled()
    assert widget.work_unit.currentData() == unit_id
    assert widget.work_unit.currentText() == "개"
    assert widget.work_add_button.isEnabled()
    assert widget.work_unit_hint.isHidden()

    widget.close()
