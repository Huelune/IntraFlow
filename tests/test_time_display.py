from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel

from intraflow.ui.time_display import TimeDisplay


def test_utc_timestamp_is_rendered_in_configured_timezone() -> None:
    QApplication.instance() or QApplication([])
    display = TimeDisplay("Asia/Seoul")

    assert display.format("2026-08-11T16:00:00Z") == "2026-08-12 01:00"
    assert display.format("2026-08-11T16:00:00Z", seconds=True) == "2026-08-12 01:00:00"
    assert "Asia/Seoul (UTC+09:00)" in display.tooltip("2026-08-11T16:00:00Z")


def test_timezone_conversion_respects_daylight_saving_time() -> None:
    QApplication.instance() or QApplication([])
    display = TimeDisplay("America/New_York")

    assert display.format("2026-01-15T12:00:00Z") == "2026-01-15 07:00"
    assert display.format("2026-07-15T12:00:00Z") == "2026-07-15 08:00"


def test_invalid_timezone_falls_back_to_system_and_sets_label_tooltip() -> None:
    QApplication.instance() or QApplication([])
    display = TimeDisplay("Invalid/Timezone")
    label = QLabel()

    display.set_label(label, "2026-08-11T16:00:00Z", seconds=True)

    assert display.configured_timezone_is_valid is False
    assert display.effective_timezone_id == display.system_timezone_id
    assert label.text()
    assert display.system_timezone_id in label.toolTip()
