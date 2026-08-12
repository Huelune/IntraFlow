from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QTableWidget

from intraflow.ui.table_view import configure_columns


def test_table_column_widths_are_persisted_per_view(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    key = "test-persisted-columns"
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    settings = QSettings(
        QSettings.Format.IniFormat, QSettings.Scope.UserScope, "IGLOO", "IntraFlow",
    )
    settings.remove(f"table-columns/v1/{key}")

    first = QTableWidget(0, 2)
    configure_columns(first, key, (120, 180))
    first.show()
    app.processEvents()
    assert first.columnWidth(0) == 120
    first.setColumnWidth(0, 246)
    QTest.qWait(300)
    app.processEvents()

    second = QTableWidget(0, 2)
    configure_columns(second, key, (120, 180))
    assert second.columnWidth(0) == 246
    assert second.wordWrap() is False

    settings.remove(f"table-columns/v1/{key}")
