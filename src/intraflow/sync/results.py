from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


SyncTargetStatus = Literal["APPLIED", "UNCHANGED", "SKIPPED", "FAILED", "CONFLICT"]


@dataclass(frozen=True, slots=True)
class SyncTargetResult:
    target_type: str
    target_id: str
    status: SyncTargetStatus
    message: str


@dataclass(frozen=True, slots=True)
class SyncOperationResult:
    operation: str
    started_at: str
    finished_at: str
    targets: tuple[SyncTargetResult, ...]

    @property
    def successful(self) -> bool:
        return not any(item.status in {"FAILED", "CONFLICT"} for item in self.targets)

    def count(self, status: SyncTargetStatus) -> int:
        return sum(item.status == status for item in self.targets)

    @property
    def summary(self) -> str:
        return (
            f"적용 {self.count('APPLIED')} · 변경 없음 {self.count('UNCHANGED')} · "
            f"건너뜀 {self.count('SKIPPED')} · 실패 {self.count('FAILED')} · "
            f"충돌 {self.count('CONFLICT')}"
        )
