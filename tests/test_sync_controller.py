from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import time

from PySide6.QtWidgets import QApplication

from intraflow.config import AppSettings, RuntimeConfig
from intraflow.ui.sync_controller import SyncController


class FakeSyncService:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def pull_all(self):
        self.calls.append("pull")
        return "pulled"

    def push_all(self):
        self.calls.append("push")
        return "pushed"

    def synchronize(self):
        self.calls.append("synchronize")
        return "synchronized"


class ImmediatePool:
    def start(self, job) -> None:
        job.run()


class HoldingPool:
    def __init__(self) -> None:
        self.job = None

    def start(self, job) -> None:
        self.job = job


def test_auto_pull_starts_after_delay_and_never_pushes(tmp_path, monkeypatch) -> None:
    QApplication.instance() or QApplication([])
    monkeypatch.setenv("INTRAFLOW_CONFIG_PATH", str(tmp_path / "local.toml"))
    service = FakeSyncService()
    runtime = RuntimeConfig("user", "device", "Z:/IntraFlow", True, 1)
    controller = SyncController(
        service, AppSettings(), runtime, startup_delay_ms=10_000, thread_pool=ImmediatePool(),
    )

    assert controller.auto_timer.isActive()
    assert controller.auto_timer.remainingTime() <= 10_000
    controller._auto_pull()

    assert service.calls == ["pull"]
    assert controller.last_success_at is not None
    assert controller.auto_timer.interval() == 60_000


def test_sync_operations_are_serialized_and_preferences_are_saved(tmp_path, monkeypatch) -> None:
    QApplication.instance() or QApplication([])
    monkeypatch.setenv("INTRAFLOW_CONFIG_PATH", str(tmp_path / "local.toml"))
    service, pool, settings = FakeSyncService(), HoldingPool(), AppSettings()
    controller = SyncController(service, settings, RuntimeConfig("user", "device", "Z:/IntraFlow"),
                                thread_pool=pool)

    assert controller.pull() is True
    assert controller.push() is False
    assert controller.busy is True
    pool.job.run()
    assert service.calls == ["pull"]
    assert controller.busy is False

    controller.set_preferences(True, 30, "Asia/Seoul")
    loaded = settings.runtime_config()
    assert loaded.auto_pull_enabled is True
    assert loaded.auto_pull_interval_minutes == 30
    assert loaded.display_timezone == "Asia/Seoul"
    assert controller.auto_timer.interval() == 30 * 60_000


def test_real_thread_pool_delivers_completion_to_ui_thread(tmp_path, monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    monkeypatch.setenv("INTRAFLOW_CONFIG_PATH", str(tmp_path / "local.toml"))
    service = FakeSyncService()
    controller = SyncController(
        service, AppSettings(), RuntimeConfig("user", "device", "Z:/IntraFlow"),
    )

    assert controller.pull() is True
    deadline = time.monotonic() + 2
    while controller.busy and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)

    assert controller.busy is False
    assert controller.last_success_at is not None
    assert controller._active_signals is None
    assert service.calls == ["pull"]
