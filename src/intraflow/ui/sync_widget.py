from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import QFormLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from intraflow.ui.sync_controller import SyncController


class SyncWidget(QWidget):
    def __init__(self, controller: SyncController, on_changed: Callable[[], None]) -> None:
        super().__init__()
        self.controller, self.on_changed = controller, on_changed
        self.last_sync, self.pending, self.state, self.error = QLabel(), QLabel(), QLabel(), QLabel()
        self.error.setProperty("status", "error")
        self.pull, self.push, self.synchronize = QPushButton("Pull"), QPushButton("Push"), QPushButton("전체 동기화")
        self.pull.clicked.connect(lambda: controller.pull(automatic=False))
        self.push.clicked.connect(controller.push)
        self.synchronize.clicked.connect(controller.synchronize)
        self.synchronize.setProperty("primary", True)
        form = QFormLayout()
        form.addRow("현재 상태", self.state)
        form.addRow("마지막 동기화", self.last_sync)
        form.addRow("Outbox 대기", self.pending)
        form.addRow("최근 오류", self.error)
        actions = QHBoxLayout()
        for button in (self.pull, self.push, self.synchronize):
            actions.addWidget(button)
        actions.addStretch()
        card = QWidget()
        card.setProperty("card", True)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        title = QLabel("NAS 동기화")
        title.setProperty("role", "title")
        card_layout.addWidget(title)
        card_layout.addLayout(form)
        card_layout.addLayout(actions)
        card_layout.addStretch()
        layout = QVBoxLayout(self)
        layout.addWidget(card)
        controller.status_changed.connect(self.refresh)
        controller.succeeded.connect(self._completed)
        controller.failed.connect(self._failed)
        self.refresh()

    def refresh(self, *_args, automatic: bool = False) -> None:
        status = self.controller.service.status() if self.controller.service else None
        self.state.setText(self.controller.status_text)
        self.last_sync.setText(status.last_sync_at if status and status.last_sync_at else "아직 동기화하지 않음")
        self.pending.setText(str(status.pending_count) if status else "-")
        self.error.setText(self.controller.last_error or (status.last_error if status else None) or "없음")
        enabled = not self.controller.busy and self.controller.service is not None
        for button in (self.pull, self.push, self.synchronize):
            button.setEnabled(enabled)

    def _completed(self, _name: str, _automatic: bool, _result: object) -> None:
        self.refresh()
        self.on_changed()

    def _failed(self, _name: str, _automatic: bool, _error: str) -> None:
        self.refresh()
