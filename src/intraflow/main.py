from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from intraflow.bootstrap import build_database
from intraflow.config import settings
from intraflow.models import Base, Device, User
from intraflow.services.assignment_service import AssignmentService
from intraflow.services.administration_service import AdministrationService
from intraflow.services.progress_service import ProgressService
from intraflow.services.setup_service import SetupService
from intraflow.sync.nas_client import NasClient
from intraflow.sync.sync_service import SyncService
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
    setup_service = SetupService(session_factory)
    setup_service.ensure_bootstrap_admin(runtime.current_user_id)
    progress = ProgressService(
        session_factory,
        current_user_id=runtime.current_user_id,
        current_device_id=runtime.current_device_id,
    )
    assignments = AssignmentService(session_factory, current_user_id=runtime.current_user_id)
    administration = AdministrationService(session_factory, current_user_id=runtime.current_user_id)
    sync_service = None
    if runtime.nas_root_path:
        sync_service = SyncService(
            session_factory, NasClient(runtime.nas_root_path), current_user_id=runtime.current_user_id,
        )
    window = MainWindow(assignments, progress, administration, sync_service)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
