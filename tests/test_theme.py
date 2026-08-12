from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from intraflow.ui.theme import DARK, LIGHT, apply_theme


def test_theme_manager_replaces_inherited_dark_palette() -> None:
    app = QApplication.instance() or QApplication([])
    inherited = QPalette()
    inherited.setColor(QPalette.ColorRole.Window, QColor("#050505"))
    inherited.setColor(QPalette.ColorRole.Base, QColor("#000000"))
    app.setPalette(inherited)

    manager = apply_theme(app)
    manager.apply(False)

    assert app.palette().color(QPalette.ColorRole.Window).name().upper() == LIGHT.background
    assert app.palette().color(QPalette.ColorRole.Base).name().upper() == LIGHT.surface
    assert "QCalendarWidget" in app.styleSheet()


def test_theme_manager_applies_complete_dark_palette() -> None:
    app = QApplication.instance() or QApplication([])
    manager = apply_theme(app)

    manager.apply(True)

    assert app.palette().color(QPalette.ColorRole.Window).name().upper() == DARK.background
    assert app.palette().color(QPalette.ColorRole.Base).name().upper() == DARK.surface
    assert app.palette().color(QPalette.ColorRole.Text).name().upper() == DARK.text
    assert DARK.accent in app.styleSheet()
    assert "border-left: 3px" not in app.styleSheet()
    assert "QCalendarWidget QToolButton" not in app.styleSheet()
