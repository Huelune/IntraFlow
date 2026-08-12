from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from intraflow.ui.sync_controller import SyncController
from intraflow.ui.time_display import TimeDisplay


class SyncWidget(QWidget):
    def __init__(
        self, controller: SyncController, on_changed: Callable[[], None],
        time_display: TimeDisplay | None = None,
    ) -> None:
        super().__init__()
        self.controller, self.on_changed = controller, on_changed
        self.time_display = time_display or TimeDisplay(controller.runtime.display_timezone)
        self.last_sync, self.pending, self.state, self.error = QLabel(), QLabel(), QLabel(), QLabel()
        self.error.setProperty("status", "error")
        self.pull = QPushButton("Pull")
        self.push = QPushButton("Push")
        self.synchronize = QPushButton("전체 동기화")
        self.resolve_conflict = QPushButton("내 업무 충돌 해결")
        self.pull.clicked.connect(lambda: controller.pull(automatic=False))
        self.push.clicked.connect(controller.push)
        self.synchronize.clicked.connect(controller.synchronize)
        self.resolve_conflict.clicked.connect(self._resolve_user_conflict)
        self.synchronize.setProperty("primary", True)
        form = QFormLayout()
        form.addRow("현재 상태", self.state)
        form.addRow("마지막 동기화", self.last_sync)
        form.addRow("Outbox 대기", self.pending)
        form.addRow("최근 오류", self.error)
        actions = QHBoxLayout()
        for button in (self.pull, self.push, self.synchronize, self.resolve_conflict):
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
        self.time_display.set_label(
            self.last_sync, status.last_sync_at if status else None,
            seconds=True, empty="아직 동기화하지 않음",
        )
        self.pending.setText(str(status.pending_count) if status else "-")
        self.error.setText(self.controller.last_error or (status.last_error if status else None) or "없음")
        enabled = not self.controller.busy and self.controller.service is not None
        for button in (self.pull, self.push, self.synchronize, self.resolve_conflict):
            button.setEnabled(enabled)

    def _completed(self, _name: str, _automatic: bool, _result: object) -> None:
        self.refresh()
        self.on_changed()

    def _failed(self, _name: str, _automatic: bool, _error: str) -> None:
        self.refresh()

    def _resolve_user_conflict(self) -> None:
        service = self.controller.service
        if service is None:
            return
        try:
            conflict = service.inspect_user_public_conflict()
        except Exception as exc:
            QMessageBox.warning(self, "충돌 확인 실패", str(exc))
            return
        if not conflict.items:
            QMessageBox.information(self, "충돌 없음", "선택이 필요한 내 업무 충돌이 없습니다.")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("내 업무 동기화 충돌 해결")
        dialog.resize(980, 520)
        table = QTableWidget(len(conflict.items), 5)
        table.setHorizontalHeaderLabels(("종류", "항목", "이 PC", "NAS", "사용할 버전"))
        choices: list[tuple[str, QComboBox]] = []
        for row, item in enumerate(conflict.items):
            for column, text in enumerate((item.kind, item.label, item.local_summary, item.nas_summary)):
                table.setItem(row, column, QTableWidgetItem(text))
            choice = QComboBox()
            choice.addItem("이 PC 유지", "LOCAL")
            choice.addItem("NAS 유지", "NAS")
            table.setCellWidget(row, 4, choice)
            choices.append((item.key, choice))
        table.resizeColumnsToContents()
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("선택 적용")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(
            "적용 전에 이 PC와 NAS snapshot을 모두 백업합니다. 적용 후 Push를 다시 실행하세요."
        ))
        layout.addWidget(table)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            backup = service.resolve_user_public_conflict({
                key: choice.currentData() for key, choice in choices
            }, expected_remote_revision=conflict.remote_revision)
        except Exception as exc:
            QMessageBox.warning(self, "충돌 해결 실패", str(exc))
            return
        QMessageBox.information(self, "충돌 선택 적용", f"원본 백업: {backup}\n이제 Push를 실행하세요.")
        self.refresh()
        self.on_changed()
