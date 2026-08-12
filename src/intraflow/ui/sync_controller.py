from __future__ import annotations

from dataclasses import replace
from typing import Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal, Slot

from intraflow.config import AppSettings, RuntimeConfig
from intraflow.sync.sync_service import SyncService
from intraflow.timeutil import utc_now_iso


class _JobSignals(QObject):
    succeeded = Signal(object)
    failed = Signal(str)


class _SyncJob(QRunnable):
    def __init__(self, action: Callable[[], object]) -> None:
        super().__init__()
        self.action = action
        self.signals = _JobSignals()

    @Slot()
    def run(self) -> None:
        try:
            result = self.action()
        except Exception as exc:
            self.signals.failed.emit(str(exc))
        else:
            self.signals.succeeded.emit(result)


class SyncController(QObject):
    """Serialize background NAS work and own the workstation auto-pull schedule."""

    started = Signal(str, bool)
    succeeded = Signal(str, bool, object)
    failed = Signal(str, bool, str)
    status_changed = Signal()
    runtime_changed = Signal(object)

    def __init__(
        self, service: SyncService | None, settings: AppSettings, runtime: RuntimeConfig,
        *, startup_delay_ms: int = 10_000, thread_pool: QThreadPool | None = None,
    ) -> None:
        super().__init__()
        self.service = service
        self.settings = settings
        self.runtime = runtime
        self.thread_pool = thread_pool or QThreadPool.globalInstance()
        self.busy = False
        self.current_operation: str | None = None
        self._active_signals: _JobSignals | None = None
        self.last_success_at: str | None = None
        self.last_error: str | None = None
        self.auto_timer = QTimer(self)
        self.auto_timer.setSingleShot(True)
        self.auto_timer.timeout.connect(self._auto_pull)
        if self.service is not None and runtime.auto_pull_enabled:
            self.auto_timer.start(startup_delay_ms)

    def set_preferences(
        self, enabled: bool, interval_minutes: int, display_timezone: str | None,
    ) -> None:
        if interval_minutes not in {1, 5, 10, 30, 60}:
            raise ValueError("자동 Pull 주기는 1, 5, 10, 30, 60분 중 하나여야 합니다.")
        self.runtime = replace(
            self.runtime, auto_pull_enabled=enabled,
            auto_pull_interval_minutes=interval_minutes,
            display_timezone=display_timezone,
        )
        self.settings.save_runtime_config(self.runtime)
        self.auto_timer.stop()
        if enabled and self.service is not None:
            self._schedule_next()
        self.runtime_changed.emit(self.runtime)
        self.status_changed.emit()

    def pull(self, *, automatic: bool = False) -> bool:
        return self._start("Pull", self.service.pull_all if self.service else None, automatic)

    def push(self) -> bool:
        return self._start("Push", self.service.push_all if self.service else None, False)

    def synchronize(self) -> bool:
        return self._start("전체 동기화", self.service.synchronize if self.service else None, False)

    def _start(self, name: str, action: Callable[[], object] | None, automatic: bool) -> bool:
        if action is None:
            self.last_error = "NAS 경로가 설정되지 않았습니다."
            self.failed.emit(name, automatic, self.last_error)
            self.status_changed.emit()
            return False
        if self.busy:
            if automatic:
                self._schedule_next()
            return False
        self.busy, self.current_operation, self.last_error = True, name, None
        self.auto_timer.stop()
        self.started.emit(name, automatic)
        self.status_changed.emit()
        job = _SyncJob(action)
        # QThreadPool may auto-delete the QRunnable before its queued signals
        # are delivered to the UI thread. Keep the signal owner alive until
        # either completion callback runs.
        self._active_signals = job.signals
        job.signals.succeeded.connect(lambda result: self._finish_success(name, automatic, result))
        job.signals.failed.connect(lambda error: self._finish_failure(name, automatic, error))
        self.thread_pool.start(job)
        return True

    @Slot()
    def _auto_pull(self) -> None:
        if not self.runtime.auto_pull_enabled:
            return
        if not self.pull(automatic=True):
            self._schedule_next()

    def _finish_success(self, name: str, automatic: bool, result: object) -> None:
        self.busy, self.current_operation = False, None
        self._active_signals = None
        self.last_success_at = utc_now_iso()
        self.last_error = None
        self.succeeded.emit(name, automatic, result)
        self.status_changed.emit()
        self._schedule_next()

    def _finish_failure(self, name: str, automatic: bool, error: str) -> None:
        self.busy, self.current_operation, self.last_error = False, None, error
        self._active_signals = None
        self.failed.emit(name, automatic, error)
        self.status_changed.emit()
        self._schedule_next()

    def _schedule_next(self) -> None:
        if self.service is not None and self.runtime.auto_pull_enabled:
            self.auto_timer.start(self.runtime.auto_pull_interval_minutes * 60_000)

    @property
    def status_text(self) -> str:
        if self.busy:
            return f"{self.current_operation} 진행 중"
        if self.last_error:
            return "동기화 오류"
        if self.last_success_at:
            return "동기화 정상"
        return "동기화 대기"
