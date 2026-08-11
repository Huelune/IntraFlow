from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from intraflow.bootstrap import build_database
from intraflow.config import settings
from intraflow.models import Base
from intraflow.services.assignment_service import AssignmentService
from intraflow.services.progress_service import ProgressService
from intraflow.sync.nas_client import NasClient
from intraflow.sync.push_service import PushService
from intraflow.ui.main_window import MainWindow


def main() -> int:
    runtime = settings.runtime_config()
    app = QApplication(sys.argv)
    if runtime.current_user_id is None:
        QMessageBox.critical(
            None,
            "IntraFlow 설정 필요",
            "intraflow.local.toml을 만들고 current_user_id를 설정하세요. "
            "intraflow.local.toml.example을 참고할 수 있습니다.",
        )
        return 2
    engine, session_factory = build_database()
    Base.metadata.create_all(engine)
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
