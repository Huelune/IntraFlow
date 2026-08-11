from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from intraflow.services.errors import SyncError


class NasClient:
    """NAS JSON storage. All paths are relative to the configured shared root."""

    def __init__(self, root_path: str | Path) -> None:
        self.root_path = Path(root_path)

    def path_for(self, *parts: str) -> Path:
        if not parts or any(not part or Path(part).is_absolute() or ".." in Path(part).parts for part in parts):
            raise SyncError("invalid NAS snapshot path")
        path = self.root_path.joinpath(*parts)
        if path.suffix != ".json":
            raise SyncError("only JSON snapshots are supported")
        return path

    def read_json(self, *parts: str) -> dict[str, Any] | None:
        path = self.path_for(*parts)
        try:
            if not path.exists():
                return None
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            raise SyncError(f"unable to read NAS snapshot {path}: {exc}") from exc
        if not isinstance(payload, dict):
            raise SyncError(f"NAS snapshot {path} must be a JSON object")
        return payload

    def exists_json(self, *parts: str) -> bool:
        return self.path_for(*parts).is_file()

    def list_project_ids(self) -> list[str]:
        directory = self.root_path / "projects"
        if not directory.is_dir():
            return []
        return sorted(path.stem for path in directory.glob("*.json") if path.is_file())

    def list_user_ids(self) -> list[str]:
        directory = self.root_path / "users"
        if not directory.is_dir():
            return []
        return sorted(path.name for path in directory.iterdir() if (path / "public.json").is_file())

    def write_json_atomic(self, payload: dict[str, Any], *parts: str) -> Path:
        path = self.path_for(*parts)
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with temporary.open("x", encoding="utf-8", newline="\n") as handle:
                json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            return path
        except OSError as exc:
            raise SyncError(f"unable to write NAS snapshot {path}: {exc}") from exc
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
