from __future__ import annotations

from typing import Any

from pydantic import ValidationError as PydanticValidationError

from intraflow.services.errors import ValidationError
from intraflow.sync.schemas import Snapshot, snapshot_adapter


class SnapshotValidator:
    def validate(self, payload: dict[str, Any]) -> Snapshot:
        try:
            return snapshot_adapter.validate_python(payload)
        except PydanticValidationError as exc:
            raise ValidationError(f"invalid sync snapshot: {exc}") from exc
