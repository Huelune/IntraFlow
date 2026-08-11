from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from intraflow.bootstrap import build_database
from intraflow.config import settings
from intraflow.models import Base, Device, User
from intraflow.services.assignment_service import AssignmentService
from intraflow.services.progress_service import ProgressService
from intraflow.services.setup_service import SetupService
from intraflow.sync.nas_client import NasClient
from intraflow.sync.push_service import PushService
from intraflow.ui.main_window import MainWindow
from intraflow.ui.setup_dialog import SetupDialog


def main() -> int:
    app = QApplication(sys.argv)
    engine, session_factory = build_database()
    Base.metadata.create_all(engine)
    runtime = settings.runtime_config()
    with session_factory() as session:
        setup_required = (
            runtime.current_user_id is None
            or session.get(User, runtime.current_user_id) is None
            or runtime.current_device_id is None
            or session.get(Device, runtime.current_device_id) is None
        )
    if setup_required:
        dialog = SetupDialog(settings, SetupService(session_factory))
        if dialog.exec() != SetupDialog.DialogCode.Accepted or dialog.runtime is None:
            return 1
        runtime = dialog.runtime
    progress = ProgressService(
        session_factory,
        current_user_id=runtime.current_user_id,
        current_device_id=runtime.current_device_id,
    )
    assignments = AssignmentService(session_factory, current_user_id=runtime.current_user_id)
    sync_now = None
    if runtime.nas_root_path:
        push = PushService(session_factory, NasClient(runtime.nas_root_path))
        sync_now = lambda: push.push_pending(current_user_id=runtime.current_user_id or "")
    window = MainWindow(assignments, progress, sync_now)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
