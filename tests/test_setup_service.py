from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from intraflow.config import AppSettings, RuntimeConfig
from intraflow.models import Device, User
from intraflow.services.setup_service import SetupService


def test_setup_provisions_user_and_device(session_factory: sessionmaker[Session]) -> None:
    identity = SetupService(session_factory).provision("tester", "Tester", "TEST-PC")

    with session_factory() as session:
        user = session.get(User, identity.user_id)
        device = session.get(Device, identity.device_id)
    assert user is not None
    assert user.user_code == "tester"
    assert user.is_system_admin == 1
    assert device is not None
    assert device.user_id == identity.user_id


def test_runtime_config_can_be_saved_and_loaded(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "intraflow.local.toml"
    monkeypatch.setenv("INTRAFLOW_CONFIG_PATH", str(config_path))
    settings = AppSettings()
    settings.save_runtime_config(RuntimeConfig(
        "user", "device", "Z:/IntraFlow", auto_pull_enabled=True,
        auto_pull_interval_minutes=30,
    ))

    loaded = settings.runtime_config()
    assert loaded.current_user_id == "user"
    assert loaded.current_device_id == "device"
    assert loaded.nas_root_path == "Z:/IntraFlow"
    assert loaded.auto_pull_enabled is True
    assert loaded.auto_pull_interval_minutes == 30
    assert not list(tmp_path.glob("*.tmp"))


def test_runtime_config_uses_safe_auto_pull_defaults(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "intraflow.local.toml"
    config_path.write_text('auto_pull_enabled = false\nauto_pull_interval_minutes = 3\n', encoding="utf-8")
    monkeypatch.setenv("INTRAFLOW_CONFIG_PATH", str(config_path))

    loaded = AppSettings().runtime_config()

    assert loaded.auto_pull_enabled is False
    assert loaded.auto_pull_interval_minutes == 5
