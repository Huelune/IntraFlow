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
    assert device is not None
    assert device.user_id == identity.user_id


def test_runtime_config_can_be_saved_and_loaded(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "intraflow.local.toml"
    monkeypatch.setenv("INTRAFLOW_CONFIG_PATH", str(config_path))
    settings = AppSettings()
    settings.save_runtime_config(RuntimeConfig("user", "device", "Z:/IntraFlow"))

    loaded = settings.runtime_config()
    assert loaded.current_user_id == "user"
    assert loaded.current_device_id == "device"
    assert loaded.nas_root_path == "Z:/IntraFlow"
