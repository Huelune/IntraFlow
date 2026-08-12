from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from intraflow.ui.sync_controller import SyncController


class AppCommandBar(QWidget):
    """Persistent sync controls shared by every main view."""

    def __init__(self, controller: SyncController, user_name: str) -> None:
        super().__init__()
        self.setObjectName("appCommandBar")
        self.setProperty("card", True)
        self.controller = controller
        title = QLabel("IntraFlow")
        title.setProperty("role", "title")
        user = QLabel(user_name)
        user.setProperty("role", "muted")
        self.auto_pull = QLabel()
        self.status = QLabel()
        self.pending = QLabel()
        for label in (self.auto_pull, self.status, self.pending):
            label.setProperty("badge", True)
        self.pull = QPushButton("Pull")
        self.push = QPushButton("Push")
        self.synchronize = QPushButton("전체 동기화")
        self.synchronize.setProperty("primary", True)
        self.pull.clicked.connect(lambda: controller.pull(automatic=False))
        self.push.clicked.connect(controller.push)
        self.synchronize.clicked.connect(controller.synchronize)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 7, 12, 7)
        layout.setSpacing(8)
        layout.addWidget(title)
        layout.addWidget(user)
        layout.addStretch()
        layout.addWidget(self.auto_pull)
        layout.addWidget(self.pending)
        layout.addWidget(self.status)
        layout.addWidget(self.pull)
        layout.addWidget(self.push)
        layout.addWidget(self.synchronize)
        controller.status_changed.connect(self.refresh)
        controller.runtime_changed.connect(lambda _runtime: self.refresh())
        self.refresh()

    def refresh(self) -> None:
        runtime = self.controller.runtime
        self.auto_pull.setText(
            f"자동 Pull {runtime.auto_pull_interval_minutes}분" if runtime.auto_pull_enabled else "자동 Pull 꺼짐",
        )
        status = self.controller.service.status() if self.controller.service else None
        self.pending.setText(f"대기 {status.pending_count}" if status else "NAS 미설정")
        self.auto_pull.setProperty("status", "active" if runtime.auto_pull_enabled else "")
        self.pending.setProperty("status", "warning" if status and status.pending_count else "")
        self.status.setText(self.controller.status_text)
        property_value = "error" if self.controller.last_error else (
            "active" if self.controller.last_success_at else ""
        )
        self.status.setProperty("status", property_value)
        for label in (self.auto_pull, self.pending, self.status):
            label.style().unpolish(label)
            label.style().polish(label)
        enabled = not self.controller.busy and self.controller.service is not None
        for button in (self.pull, self.push, self.synchronize):
            button.setEnabled(enabled)
