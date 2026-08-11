from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QMessageBox, QVBoxLayout

from intraflow.config import AppSettings, RuntimeConfig
from intraflow.services.errors import IntraFlowError
from intraflow.services.setup_service import SetupService


class SetupDialog(QDialog):
    def __init__(self, settings: AppSettings, setup: SetupService) -> None:
        super().__init__()
        self.settings, self.setup = settings, setup
        self.runtime: RuntimeConfig | None = None
        self.setWindowTitle("IntraFlow 최초 설정")
        self.setModal(True)
        self.user_code = QLineEdit(placeholderText="예: honggildong")
        self.display_name = QLineEdit(placeholderText="예: 홍길동")
        self.device_name = QLineEdit(placeholderText="비워두면 현재 PC 이름 사용")
        self.nas_root = QLineEdit(placeholderText="예: Z:/IntraFlow (선택)")
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form = QFormLayout()
        form.addRow("사용자 코드", self.user_code)
        form.addRow("표시 이름", self.display_name)
        form.addRow("현재 PC 이름", self.device_name)
        form.addRow("NAS 경로", self.nas_root)
        form.addRow(buttons)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("새 사용자 코드를 입력하거나, 이미 받은 사용자 코드를 입력해 이 PC를 연결하세요."))
        layout.addLayout(form)

    def accept(self) -> None:
        try:
            identity = self.setup.provision(self.user_code.text(), self.display_name.text(), self.device_name.text() or None)
            self.runtime = RuntimeConfig(identity.user_id, identity.device_id, self.nas_root.text().strip() or None)
            self.settings.save_runtime_config(self.runtime)
        except (IntraFlowError, OSError) as exc:
            QMessageBox.warning(self, "최초 설정 실패", str(exc))
            return
        super().accept()
