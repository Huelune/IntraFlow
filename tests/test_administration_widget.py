from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from sqlalchemy.orm import Session, sessionmaker

from intraflow.ui.administration_widget import AdministrationWidget
from workflow import build_workflow


def test_administration_tree_shows_hierarchy_and_read_only_owner(
    session_factory: sessionmaker[Session],
) -> None:
    app = QApplication.instance() or QApplication([])
    _identity, admin, work, _project, _part, _item = build_workflow(session_factory)
    widget = AdministrationWidget(admin, work, lambda: None)
    widget.show()
    app.processEvents()
    project = widget.tree.topLevelItem(0)
    assert project.text(0) == "프로젝트"
    assert project.child(0).text(0) == "파트"
    assert project.child(0).child(0).text(0) == "업무"
    assert project.child(0).child(0).text(1) == "Owner"
    widget.close()
