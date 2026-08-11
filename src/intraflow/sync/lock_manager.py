from __future__ import annotations

import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from intraflow.services.errors import SyncError


class LockManager:
    def __init__(self, root_path: str | Path, *, timeout_seconds: float = 5.0) -> None:
        self.root_path = Path(root_path)
        self.timeout_seconds = timeout_seconds

    @contextmanager
    def acquire(self, resource: str) -> Iterator[None]:
        if not resource or any(character in resource for character in "\\/:"):
            raise SyncError("invalid lock resource")
        lock_path = self.root_path / ".locks" / f"{resource}.lock"
        deadline = time.monotonic() + self.timeout_seconds
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        while True:
            try:
                descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(descriptor)
                break
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise SyncError(f"timed out waiting for NAS lock: {resource}")
                time.sleep(0.1)
            except OSError as exc:
                raise SyncError(f"unable to create NAS lock {resource}: {exc}") from exc
        try:
            yield
        finally:
            try:
                lock_path.unlink(missing_ok=True)
            except OSError:
                pass
