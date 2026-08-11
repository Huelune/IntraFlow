from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from sqlalchemy.orm import Session, sessionmaker

from intraflow.ui.dialogs import PartDialog, ProjectDialog, WorkItemDialog
from workflow import build_workflow


def test_definition_dialogs_make_create_and_edit_modes_explicit(
    session_factory: sessionmaker[Session],
) -> None:
    QApplication.instance() or QApplication([])
    _identity, admin, work, project_id, part_id, item = build_workflow(session_factory)
    projects = {project.id: project for project in admin.list_projects()}
    parts = {part.id: part for part in admin.list_parts()}

    new_work = WorkItemDialog(work)
    edit_work = WorkItemDialog(work, item)
    new_project = ProjectDialog(admin)
    edit_part = PartDialog(admin, projects[project_id], parts[part_id])

    assert (new_work.windowTitle(), new_work.save_button.text()) == ("새 업무", "추가")
    assert (edit_work.windowTitle(), edit_work.save_button.text()) == ("업무 수정", "변경 저장")
    assert edit_work.name.text() == item.name
    assert (new_project.windowTitle(), new_project.save_button.text()) == ("새 프로젝트", "추가")
    assert (edit_part.windowTitle(), edit_part.save_button.text()) == ("파트 수정", "변경 저장")
    for dialog in (new_work, edit_work, new_project, edit_part):
        dialog.close()
