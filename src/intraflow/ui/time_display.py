from __future__ import annotations

from PySide6.QtCore import QDateTime, Qt, QTimeZone
from PySide6.QtWidgets import QLabel


def _zone_id(value: bytes | bytearray) -> str:
    return bytes(value).decode("utf-8")


class TimeDisplay:
    """Convert UTC timestamps to the workstation's configured display zone."""

    def __init__(self, timezone_id: str | None = None) -> None:
        self.timezone_id = timezone_id

    def set_timezone(self, timezone_id: str | None) -> None:
        self.timezone_id = timezone_id

    @property
    def system_timezone_id(self) -> str:
        return _zone_id(QTimeZone.systemTimeZoneId())

    @property
    def configured_timezone_is_valid(self) -> bool:
        return self.timezone_id is None or QTimeZone(self.timezone_id.encode("utf-8")).isValid()

    @property
    def effective_timezone_id(self) -> str:
        if self.timezone_id:
            configured = QTimeZone(self.timezone_id.encode("utf-8"))
            if configured.isValid():
                return self.timezone_id
        return self.system_timezone_id

    def available_timezone_ids(self) -> list[str]:
        return sorted(_zone_id(value) for value in QTimeZone.availableTimeZoneIds())

    def format(self, value: str | None, *, seconds: bool = False, empty: str = "-") -> str:
        converted = self._convert(value)
        if converted is None:
            return empty if not value else value
        pattern = "yyyy-MM-dd HH:mm:ss" if seconds else "yyyy-MM-dd HH:mm"
        return converted.toString(pattern)

    def tooltip(self, value: str | None) -> str:
        converted = self._convert(value)
        if converted is None:
            return ""
        offset = converted.offsetFromUtc()
        sign = "+" if offset >= 0 else "-"
        offset = abs(offset)
        hours, minutes = divmod(offset // 60, 60)
        return f"{converted.toString('yyyy-MM-dd HH:mm:ss')} {self.effective_timezone_id} (UTC{sign}{hours:02d}:{minutes:02d})"

    def set_label(
        self, label: QLabel, value: str | None, *, seconds: bool = False, empty: str = "-",
    ) -> None:
        label.setText(self.format(value, seconds=seconds, empty=empty))
        label.setToolTip(self.tooltip(value))

    def now(self, *, seconds: bool = False) -> str:
        pattern = "yyyy-MM-dd HH:mm:ss" if seconds else "yyyy-MM-dd HH:mm"
        return QDateTime.currentDateTimeUtc().toTimeZone(self._timezone()).toString(pattern)

    def _timezone(self) -> QTimeZone:
        zone = QTimeZone(self.effective_timezone_id.encode("utf-8"))
        return zone if zone.isValid() else QTimeZone.systemTimeZone()

    def _convert(self, value: str | None) -> QDateTime | None:
        if not value:
            return None
        parsed = QDateTime.fromString(value, Qt.DateFormat.ISODate)
        if not parsed.isValid():
            return None
        if parsed.timeSpec() == Qt.TimeSpec.LocalTime:
            parsed.setTimeZone(QTimeZone.utc())
        return parsed.toTimeZone(self._timezone())
