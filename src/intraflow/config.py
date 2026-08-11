from __future__ import annotations

import os
import json
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AppSettings:
    app_name: str = "IntraFlow"
    db_filename: str = "intraflow.db"
    config_filename: str = "intraflow.local.toml"

    @property
    def data_dir(self) -> Path:
        local_app_data = os.getenv("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data) / self.app_name
        return Path.home() / ".intraflow"

    @property
    def db_path(self) -> Path:
        return self.data_dir / self.db_filename

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.db_path.as_posix()}"

    @property
    def config_path(self) -> Path:
        configured = os.getenv("INTRAFLOW_CONFIG_PATH")
        return Path(configured) if configured else Path.cwd() / self.config_filename

    def runtime_config(self) -> "RuntimeConfig":
        values: dict[str, object] = {}
        if self.config_path.exists():
            with self.config_path.open("rb") as handle:
                values = tomllib.load(handle)
        return RuntimeConfig(
            current_user_id=os.getenv("INTRAFLOW_CURRENT_USER_ID", str(values.get("current_user_id", ""))) or None,
            current_device_id=os.getenv("INTRAFLOW_CURRENT_DEVICE_ID", str(values.get("current_device_id", ""))) or None,
            nas_root_path=os.getenv("INTRAFLOW_NAS_ROOT_PATH", str(values.get("nas_root_path", ""))) or None,
        )

    def save_runtime_config(self, runtime: "RuntimeConfig") -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        content = "\n".join([
            f"current_user_id = {json.dumps(runtime.current_user_id or '')}",
            f"current_device_id = {json.dumps(runtime.current_device_id or '')}",
            f"nas_root_path = {json.dumps(runtime.nas_root_path or '')}",
            "",
        ])
        self.config_path.write_text(content, encoding="utf-8", newline="\n")


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    current_user_id: str | None
    current_device_id: str | None
    nas_root_path: str | None

    def require_user_id(self) -> str:
        if not self.current_user_id:
            raise ValueError("current_user_id must be configured in intraflow.local.toml")
        return self.current_user_id


settings = AppSettings()
