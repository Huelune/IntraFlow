from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import QGridLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget

from intraflow.services.errors import IntraFlowError
from intraflow.sync.sync_service import SyncService


class SyncWidget(QWidget):
    def __init__(self, service: SyncService, on_changed: Callable[[], None]) -> None:
        super().__init__()
        self.service = service
        self.on_changed = on_changed
        self.last_sync = QLabel()
        self.pending = QLabel()
        self.error = QLabel()
        pull, push, synchronize = QPushButton("Pull"), QPushButton("Push"), QPushButton("전체 동기화")
        pull.clicked.connect(lambda: self._run("Pull", self.service.pull_all))
        push.clicked.connect(lambda: self._run("Push", self.service.push_all))
        synchronize.clicked.connect(lambda: self._run("전체 동기화", self.service.synchronize))
        status = QGridLayout()
        status.addWidget(QLabel("마지막 동기화"), 0, 0)
        status.addWidget(self.last_sync, 0, 1)
        status.addWidget(QLabel("대기 항목"), 1, 0)
        status.addWidget(self.pending, 1, 1)
        status.addWidget(QLabel("최근 오류"), 2, 0)
        status.addWidget(self.error, 2, 1)
        status.addWidget(pull, 3, 0)
        status.addWidget(push, 3, 1)
        status.addWidget(synchronize, 4, 0, 1, 2)
        layout = QVBoxLayout(self)
        layout.addLayout(status)
        layout.addStretch()
        self.refresh()

    def refresh(self) -> None:
        status = self.service.status()
        self.last_sync.setText(status.last_sync_at or "아직 동기화하지 않음")
        self.pending.setText(str(status.pending_count))
        self.error.setText(status.last_error or "없음")

    def _run(self, title: str, action: Callable[[], object]) -> None:
        try:
            result = action()
        except IntraFlowError as exc:
            QMessageBox.warning(self, f"{title} 실패", f"로컬 데이터는 유지됩니다.\n{exc}")
        else:
            QMessageBox.information(self, title, f"처리 결과: {result}")
        self.refresh()
        self.on_changed()
