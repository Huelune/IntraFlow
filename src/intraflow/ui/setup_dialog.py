from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QMessageBox

from intraflow.config import AppSettings, RuntimeConfig
from intraflow.services.errors import IntraFlowError
from intraflow.services.setup_service import SetupService


class SetupDialog(QDialog):
    def __init__(self, settings: AppSettings, setup: SetupService) -> None:
        super().__init__()
        self.settings = settings
        self.setup = setup
        self.runtime: RuntimeConfig | None = None
        self.setWindowTitle("IntraFlow 최초 설정")
        self.setModal(True)
        self.user_code = QLineEdit()
        self.user_code.setPlaceholderText("예: honggildong")
        self.display_name = QLineEdit()
        self.display_name.setPlaceholderText("예: 홍길동")
        self.device_name = QLineEdit()
        self.device_name.setPlaceholderText("비워두면 PC 이름 사용")
        self.nas_root = QLineEdit()
        self.nas_root.setPlaceholderText("예: Z:/IntraFlow (선택)")
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form = QFormLayout(self)
        form.addRow("사용자 코드", self.user_code)
        form.addRow("표시 이름", self.display_name)
        form.addRow("이 PC 이름", self.device_name)
        form.addRow("NAS 경로", self.nas_root)
        form.addRow(buttons)

    def accept(self) -> None:
        try:
            identity = self.setup.provision(
                self.user_code.text(),
                self.display_name.text(),
                self.device_name.text() or None,
            )
            self.runtime = RuntimeConfig(
                current_user_id=identity.user_id,
                current_device_id=identity.device_id,
                nas_root_path=self.nas_root.text().strip() or None,
            )
            self.settings.save_runtime_config(self.runtime)
        except (IntraFlowError, OSError) as exc:
            QMessageBox.warning(self, "최초 설정 실패", str(exc))
            return
        super().accept()
