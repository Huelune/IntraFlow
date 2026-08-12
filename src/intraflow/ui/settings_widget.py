from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from intraflow.ui.sync_controller import SyncController
from intraflow.ui.time_display import TimeDisplay


class PersonalSettingsWidget(QWidget):
    def __init__(self, controller: SyncController, time_display: TimeDisplay | None = None) -> None:
        super().__init__()
        self.controller = controller
        self.time_display = time_display or TimeDisplay(controller.runtime.display_timezone)
        self._loading = False
        self._dirty = False
        self.enabled = QCheckBox("자동 Pull 사용")
        self.interval = QComboBox()
        for minutes in (1, 5, 10, 30, 60):
            self.interval.addItem(f"{minutes}분", minutes)
        self.timezone = QComboBox()
        self.timezone.setEditable(True)
        self.timezone.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.timezone.addItem(
            f"시스템 기본 ({self.time_display.system_timezone_id})", None,
        )
        for timezone_id in self.time_display.available_timezone_ids():
            self.timezone.addItem(timezone_id, timezone_id)
        if self.timezone.completer() is not None:
            self.timezone.completer().setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            self.timezone.completer().setFilterMode(Qt.MatchFlag.MatchContains)
        self.timezone_error = QLabel()
        self.timezone_error.setProperty("status", "warning")
        self.nas_path = QLabel(controller.runtime.nas_root_path or "설정되지 않음")
        self.nas_path.setTextInteractionFlags(
            self.nas_path.textInteractionFlags() | Qt.TextInteractionFlag.TextSelectableByMouse)
        self.state, self.last_success, self.error = QLabel(), QLabel(), QLabel()
        self.error.setProperty("status", "error")
        save, pull_now = QPushButton("설정 저장"), QPushButton("지금 Pull")
        save.setProperty("primary", True)
        save.clicked.connect(self.save)
        pull_now.clicked.connect(lambda: controller.pull(automatic=False))
        self.pull_now = pull_now
        form = QFormLayout()
        form.addRow("자동 Pull", self.enabled)
        form.addRow("실행 주기", self.interval)
        form.addRow("표시 시간대", self.timezone)
        form.addRow("시간대 상태", self.timezone_error)
        form.addRow("NAS 경로", self.nas_path)
        form.addRow("현재 상태", self.state)
        form.addRow("마지막 성공", self.last_success)
        form.addRow("최근 오류", self.error)
        actions = QHBoxLayout()
        actions.addWidget(save)
        actions.addWidget(pull_now)
        actions.addStretch()
        card = QWidget()
        card.setProperty("card", True)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        title = QLabel("개인 동기화 설정")
        title.setProperty("role", "title")
        description = QLabel("자동 Pull은 이 PC의 로컬 설정이며 Push를 자동 실행하지 않습니다.")
        description.setProperty("role", "muted")
        card_layout.addWidget(title)
        card_layout.addWidget(description)
        card_layout.addSpacing(8)
        card_layout.addLayout(form)
        card_layout.addLayout(actions)
        card_layout.addStretch()
        layout = QVBoxLayout(self)
        layout.addWidget(card)
        controller.status_changed.connect(self.refresh)
        controller.runtime_changed.connect(lambda _runtime: self.refresh())
        self.enabled.toggled.connect(self._mark_dirty)
        self.interval.currentIndexChanged.connect(self._mark_dirty)
        self.timezone.currentIndexChanged.connect(self._mark_dirty)
        self.refresh()

    def save(self) -> None:
        self.controller.set_preferences(
            self.enabled.isChecked(), self.interval.currentData(), self.timezone.currentData(),
        )
        self._dirty = False
        self.refresh()

    def refresh(self, *_args, automatic: bool = False) -> None:
        runtime = self.controller.runtime
        if not self._dirty:
            self._loading = True
            self.enabled.setChecked(runtime.auto_pull_enabled)
            index = self.interval.findData(runtime.auto_pull_interval_minutes)
            if index >= 0:
                self.interval.setCurrentIndex(index)
            timezone_index = self.timezone.findData(runtime.display_timezone)
            self.timezone.setCurrentIndex(timezone_index if timezone_index >= 0 else 0)
            self._loading = False
        self.state.setText(self.controller.status_text)
        self.time_display.set_label(
            self.last_success, self.controller.last_success_at,
            seconds=True, empty="아직 성공한 Pull 없음",
        )
        self.timezone_error.setText(
            "" if self.time_display.configured_timezone_is_valid
            else f"알 수 없는 시간대입니다. 시스템 기본값({self.time_display.system_timezone_id})으로 표시합니다."
        )
        self.error.setText(self.controller.last_error or "없음")
        self.pull_now.setEnabled(not self.controller.busy and self.controller.service is not None)

    def _mark_dirty(self, *_args) -> None:
        if not self._loading:
            self._dirty = True
