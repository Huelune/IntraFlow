from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot
from PySide6.QtWidgets import (
    QButtonGroup, QDialog, QDialogButtonBox, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPushButton, QRadioButton, QVBoxLayout,
)

from intraflow.config import AppSettings, RuntimeConfig
from intraflow.services.errors import IntraFlowError
from intraflow.services.setup_service import SetupService
from intraflow.sync.nas_client import NasClient
from intraflow.sync.team_join_service import LocalJoinRecoveryService, TeamJoinService


class _JoinSignals(QObject):
    succeeded = Signal(object)
    failed = Signal(str)


class _JoinJob(QRunnable):
    def __init__(self, action) -> None:
        super().__init__()
        self.action = action
        self.signals = _JoinSignals()

    @Slot()
    def run(self) -> None:
        try:
            result = self.action()
        except Exception as exc:
            self.signals.failed.emit(str(exc))
        else:
            self.signals.succeeded.emit(result)


class SetupDialog(QDialog):
    def __init__(self, settings: AppSettings, setup: SetupService) -> None:
        super().__init__()
        self.settings, self.setup = settings, setup
        self.join_service = TeamJoinService(setup.session_factory)
        self.recovery_service = LocalJoinRecoveryService(setup.session_factory, settings)
        self.runtime: RuntimeConfig | None = None
        self.joined_existing_team = False
        self._join_signals: _JoinSignals | None = None
        self.setWindowTitle("IntraFlow 최초 설정")
        self.setModal(True)
        self.resize(620, 430)

        self.start_mode = QRadioButton("새 팀 시작")
        self.join_mode = QRadioButton("기존 팀 합류")
        self.start_mode.setChecked(True)
        modes = QButtonGroup(self)
        modes.addButton(self.start_mode)
        modes.addButton(self.join_mode)
        mode_row = QHBoxLayout()
        mode_row.addWidget(self.start_mode)
        mode_row.addWidget(self.join_mode)
        mode_row.addStretch()

        self.user_code = QLineEdit(placeholderText="예: honggildong")
        self.display_name = QLineEdit(placeholderText="새 팀 시작 시 표시 이름")
        self.device_name = QLineEdit(placeholderText="비워두면 현재 PC 이름 사용")
        self.nas_root = QLineEdit(placeholderText="예: Z:/IntraFlow")
        self.check_nas = QPushButton("NAS 연결 확인")
        self.check_nas.clicked.connect(self._inspect_team)
        nas_row = QHBoxLayout()
        nas_row.addWidget(self.nas_root, 1)
        nas_row.addWidget(self.check_nas)
        self.preview = QLabel("기존 팀 합류 전에 NAS 연결을 확인하세요.")
        self.preview.setWordWrap(True)
        self.preview.setProperty("role", "muted")

        form = QFormLayout()
        form.addRow("사용자 코드", self.user_code)
        form.addRow("표시 이름", self.display_name)
        form.addRow("현재 PC 이름", self.device_name)
        form.addRow("NAS 경로", nas_row)
        form.addRow("연결 상태", self.preview)
        box = QGroupBox("워크스테이션 연결")
        box.setLayout(form)

        self.recover = QPushButton("잘못된 로컬 설정 백업 후 기존 팀 합류")
        self.recover.setProperty("danger", True)
        self.recover.clicked.connect(self._recover_local_setup)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.ok_button.setText("새 팀 시작")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        title = QLabel("이 PC에서 IntraFlow를 어떻게 시작할지 선택하세요.")
        title.setProperty("role", "title")
        layout.addWidget(title)
        layout.addLayout(mode_row)
        layout.addWidget(box)
        layout.addWidget(self.recover)
        layout.addStretch()
        layout.addWidget(buttons)
        self.start_mode.toggled.connect(self._mode_changed)
        self._mode_changed()

    def _mode_changed(self) -> None:
        joining = self.join_mode.isChecked()
        self.display_name.setVisible(not joining)
        label = self._form_label(self.display_name)
        if label is not None:
            label.setVisible(not joining)
        self.check_nas.setVisible(joining)
        self.preview.setText(
            "NAS에서 사용자를 먼저 확인한 뒤 이 PC만 연결합니다."
            if joining else "NAS에 기존 users.json이 있으면 새 팀을 시작할 수 없습니다."
        )
        self.ok_button.setText("이 PC 연결" if joining else "새 팀 시작")

    def _form_label(self, widget):
        layout = widget.parentWidget().layout()
        return layout.labelForField(widget) if isinstance(layout, QFormLayout) else None

    def _inspect_team(self) -> None:
        self.check_nas.setEnabled(False)
        self.preview.setText("NAS 연결과 snapshot을 확인하는 중입니다…")
        job = _JoinJob(lambda: self.join_service.inspect_team(self.nas_root.text()))
        self._join_signals = job.signals
        job.signals.succeeded.connect(self._inspect_succeeded)
        job.signals.failed.connect(self._inspect_failed)
        QThreadPool.globalInstance().start(job)

    def _inspect_succeeded(self, preview) -> None:
        self._join_signals = None
        self.check_nas.setEnabled(True)
        warning = f" / 경고: {'; '.join(preview.warnings)}" if preview.warnings else ""
        self.preview.setText(
            f"사용자 {preview.user_count}명 · 단위 {preview.unit_count}개 · "
            f"프로젝트 {preview.project_count}개 · 공개 업무 파일 {preview.public_snapshot_count}개{warning}"
        )

    def _inspect_failed(self, error: str) -> None:
        self._join_signals = None
        self.check_nas.setEnabled(True)
        self.preview.setText(f"연결 실패: {error}")

    def accept(self) -> None:
        if self.join_mode.isChecked():
            self._start_join()
            return
        try:
            root_value = self.nas_root.text().strip()
            if root_value:
                nas = NasClient(Path(root_value).expanduser().resolve())
                if nas.exists_json("users.json"):
                    raise IntraFlowError("NAS에 기존 팀이 있습니다. 기존 팀 합류를 선택하세요.")
            identity = self.setup.start_new_team(
                self.user_code.text(), self.display_name.text(), self.device_name.text() or None,
            )
            self.runtime = RuntimeConfig(identity.user_id, identity.device_id, root_value or None)
            self.settings.save_runtime_config(self.runtime)
        except (IntraFlowError, OSError) as exc:
            QMessageBox.warning(self, "최초 설정 실패", str(exc))
            return
        super().accept()

    def _start_join(self) -> None:
        self.ok_button.setEnabled(False)
        self.check_nas.setEnabled(False)
        self.preview.setText("NAS 데이터를 확인하고 이 PC에 적용하는 중입니다…")
        job = _JoinJob(lambda: self.join_service.join_existing_team(
            self.nas_root.text(), self.user_code.text(), self.device_name.text(),
        ))
        self._join_signals = job.signals
        job.signals.succeeded.connect(self._join_succeeded)
        job.signals.failed.connect(self._join_failed)
        QThreadPool.globalInstance().start(job)

    def _join_succeeded(self, runtime: RuntimeConfig) -> None:
        self._join_signals = None
        self.runtime = runtime
        self.joined_existing_team = True
        self.settings.save_runtime_config(runtime)
        super().accept()

    def _join_failed(self, error: str) -> None:
        self._join_signals = None
        self.ok_button.setEnabled(True)
        self.check_nas.setEnabled(True)
        self.preview.setText(f"연결 실패: {error}")
        QMessageBox.warning(self, "최초 설정 실패", error)

    def _recover_local_setup(self) -> None:
        answer = QMessageBox.question(
            self, "로컬 설정 초기화",
            "업무나 원격 반영 흔적이 없는 경우에만 DB를 백업하고 로컬 설정을 초기화합니다. 계속할까요?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            backup = self.recovery_service.reset_for_join(self.nas_root.text().strip() or None)
        except (IntraFlowError, OSError) as exc:
            QMessageBox.warning(self, "초기화 불가", str(exc))
            return
        self.join_mode.setChecked(True)
        QMessageBox.information(self, "백업 완료", f"로컬 DB를 백업했습니다.\n{backup}")
