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
        self.last_pull, self.last_push, self.pending, self.state, self.error = (
            QLabel(), QLabel(), QLabel(), QLabel(), QLabel(),
        )
        self.error.setProperty("status", "error")
        self.pull = QPushButton("Pull")
        self.push = QPushButton("Push")
        self.synchronize = QPushButton("전체 동기화")
        self.resolve_conflict = QPushButton("내 업무 충돌 해결")
        self.resolve_shared = QPushButton("공유 정의 충돌 해결")
        self.pull.clicked.connect(lambda: controller.pull(automatic=False))
        self.push.clicked.connect(controller.push)
        self.synchronize.clicked.connect(controller.synchronize)
        self.resolve_conflict.clicked.connect(self._resolve_user_conflict)
        self.resolve_shared.clicked.connect(self._resolve_shared_conflicts)
        self.synchronize.setProperty("primary", True)
        form = QFormLayout()
        form.addRow("현재 상태", self.state)
        form.addRow("마지막 Pull", self.last_pull)
        form.addRow("마지막 Push", self.last_push)
        form.addRow("Outbox 대기", self.pending)
        form.addRow("최근 오류", self.error)
        actions = QHBoxLayout()
        for button in (self.pull, self.push, self.synchronize, self.resolve_conflict, self.resolve_shared):
            actions.addWidget(button)
        actions.addStretch()
        self.results = QTableWidget(0, 4)
        self.results.setHorizontalHeaderLabels(("대상", "ID", "결과", "메시지"))
        self.results.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        card = QWidget()
        card.setProperty("card", True)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        title = QLabel("NAS 동기화")
        title.setProperty("role", "title")
        card_layout.addWidget(title)
        card_layout.addLayout(form)
        card_layout.addLayout(actions)
        card_layout.addWidget(QLabel("최근 실행 결과"))
        card_layout.addWidget(self.results)
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
            self.last_pull, status.last_pull_at if status else None,
            seconds=True, empty="아직 Pull하지 않음",
        )
        self.time_display.set_label(
            self.last_push, status.last_push_at if status else None,
            seconds=True, empty="아직 Push하지 않음",
        )
        self.pending.setText(str(status.pending_count) if status else "-")
        self.error.setText(self.controller.last_error or (status.last_error if status else None) or "없음")
        enabled = not self.controller.busy and self.controller.service is not None
        for button in (self.pull, self.push, self.synchronize, self.resolve_conflict, self.resolve_shared):
            button.setEnabled(enabled)
        result = self.controller.last_result
        self.results.setRowCount(len(result.targets) if result else 0)
        if result:
            labels = {
                "APPLIED": "반영", "UNCHANGED": "최신", "SKIPPED": "건너뜀",
                "FAILED": "실패", "CONFLICT": "충돌",
            }
            for row, item in enumerate(result.targets):
                for column, value in enumerate((
                    item.target_type, item.target_id, labels[item.status], item.message,
                )):
                    self.results.setItem(row, column, QTableWidgetItem(value))

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

    def _resolve_shared_conflicts(self) -> None:
        service = self.controller.service
        if service is None:
            return
        try:
            conflicts = service.inspect_shared_conflicts()
        except Exception as exc:
            QMessageBox.warning(self, "충돌 확인 실패", str(exc))
            return
        if conflicts.target_count == 0:
            QMessageBox.information(self, "충돌 없음", "선택이 필요한 공유 정의 충돌이 없습니다.")
            return
        if not conflicts.items:
            try:
                backup = service.resolve_shared_conflicts({})
            except Exception as exc:
                QMessageBox.warning(self, "자동 병합 실패", str(exc))
                return
            QMessageBox.information(self, "자동 병합 완료", f"서로 다른 항목의 변경을 병합했습니다.\n원본 백업: {backup}")
            self.refresh()
            self.on_changed()
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("공유 정의 충돌 해결")
        dialog.resize(1000, 560)
        table = QTableWidget(len(conflicts.items), 6)
        table.setHorizontalHeaderLabels(("대상", "항목", "이 PC", "NAS", "사용할 버전", "ID"))
        choices: list[tuple[str, QComboBox]] = []
        for row, item in enumerate(conflicts.items):
            for column, text in enumerate((
                item.target_type, item.label, item.local_summary, item.nas_summary,
            )):
                table.setItem(row, column, QTableWidgetItem(text))
            choice = QComboBox()
            choice.addItem("이 PC 유지", "LOCAL")
            choice.addItem("NAS 유지", "NAS")
            table.setCellWidget(row, 4, choice)
            table.setItem(row, 5, QTableWidgetItem(item.target_id))
            choices.append((item.key, choice))
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel,
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("선택 적용")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(
            "한쪽에서만 변경된 항목은 자동 병합합니다. 아래에는 양쪽에서 모두 변경된 항목만 표시됩니다.",
        ))
        layout.addWidget(table)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            backup = service.resolve_shared_conflicts({
                key: choice.currentData() for key, choice in choices
            })
        except Exception as exc:
            QMessageBox.warning(self, "충돌 해결 실패", str(exc))
            return
        QMessageBox.information(self, "충돌 선택 적용", f"원본 백업: {backup}\n이제 Push를 실행하세요.")
        self.refresh()
        self.on_changed()
