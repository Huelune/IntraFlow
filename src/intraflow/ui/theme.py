from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, Qt, Slot
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


IGLOO_GREEN = "#00A98E"
PRIMARY_GREEN = "#006B5B"


@dataclass(frozen=True, slots=True)
class ThemeTokens:
    background: str
    surface: str
    elevated: str
    border: str
    text: str
    muted: str
    accent: str
    primary: str
    primary_text: str
    selection: str
    warning: str
    warning_surface: str
    danger: str
    input_border: str
    disabled_text: str
    disabled_surface: str


LIGHT = ThemeTokens(
    background="#F4F6F6", surface="#FFFFFF", elevated="#EEF1F1", border="#D9DEDE",
    text="#171A1A", muted="#687071", accent=IGLOO_GREEN, primary=PRIMARY_GREEN,
    primary_text="#FFFFFF", selection="#DDF4EF", warning="#B66A00", warning_surface="#FFF3D6",
    danger="#B42318",
    input_border="#BBC4C3", disabled_text="#A0A7A7", disabled_surface="#F0F2F2",
)
DARK = ThemeTokens(
    background="#111716", surface="#18211F", elevated="#202B28", border="#344440",
    text="#F2F7F6", muted="#A6B2AF", accent=IGLOO_GREEN, primary=IGLOO_GREEN,
    primary_text="#07110F", selection="#163B34", warning="#F5B84B", warning_surface="#3A2D18",
    danger="#FF6B6B",
    input_border="#50625E", disabled_text="#75827F", disabled_surface="#242E2C",
)


class ThemeManager(QObject):
    def __init__(self, app: QApplication) -> None:
        super().__init__(app)
        self.app = app
        self.is_dark = self._initial_dark()
        app.setStyle("Fusion")
        app.styleHints().colorSchemeChanged.connect(self._scheme_changed)
        self.apply(self.is_dark)

    def _initial_dark(self) -> bool:
        scheme = self.app.styleHints().colorScheme()
        if scheme == Qt.ColorScheme.Dark:
            return True
        if scheme == Qt.ColorScheme.Light:
            return False
        return self.app.palette().color(QPalette.ColorRole.Window).lightness() < 128

    @Slot(Qt.ColorScheme)
    def _scheme_changed(self, scheme: Qt.ColorScheme) -> None:
        if scheme == Qt.ColorScheme.Unknown:
            return
        self.apply(scheme == Qt.ColorScheme.Dark)

    def apply(self, dark: bool) -> None:
        self.is_dark = dark
        tokens = DARK if dark else LIGHT
        self.app.setPalette(_palette(tokens))
        self.app.setStyleSheet(_style_sheet(tokens))


def _palette(tokens: ThemeTokens) -> QPalette:
    palette = QPalette()
    roles = {
        QPalette.ColorRole.Window: tokens.background,
        QPalette.ColorRole.WindowText: tokens.text,
        QPalette.ColorRole.Base: tokens.surface,
        QPalette.ColorRole.AlternateBase: tokens.elevated,
        QPalette.ColorRole.ToolTipBase: tokens.elevated,
        QPalette.ColorRole.ToolTipText: tokens.text,
        QPalette.ColorRole.Text: tokens.text,
        QPalette.ColorRole.Button: tokens.surface,
        QPalette.ColorRole.ButtonText: tokens.text,
        QPalette.ColorRole.BrightText: tokens.danger,
        QPalette.ColorRole.Highlight: tokens.accent,
        QPalette.ColorRole.HighlightedText: tokens.primary_text,
        QPalette.ColorRole.PlaceholderText: tokens.muted,
    }
    for role, color in roles.items():
        palette.setColor(QPalette.ColorGroup.All, role, QColor(color))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(tokens.disabled_text))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(tokens.disabled_text))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(tokens.disabled_text))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Button, QColor(tokens.disabled_surface))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Base, QColor(tokens.disabled_surface))
    return palette


def _style_sheet(t: ThemeTokens) -> str:
    return f"""
QWidget {{ color: {t.text}; font-family: "Malgun Gothic", "Segoe UI"; font-size: 10pt; }}
QMainWindow, QWidget#appRoot, QDialog, QMessageBox {{ background: {t.background}; }}
QWidget[card="true"] {{ background: {t.surface}; border: 1px solid {t.border}; border-radius: 8px; }}
QWidget#appCommandBar {{ border-radius: 8px; }}
QLabel[role="title"] {{ font-size: 17pt; font-weight: 700; color: {t.text}; }}
QLabel[role="section"] {{ font-size: 12pt; font-weight: 700; color: {t.text}; }}
QLabel[role="muted"] {{ color: {t.muted}; }}
QLabel[status="active"] {{ color: {t.accent}; font-weight: 700; }}
QLabel[status="warning"] {{ color: {t.warning}; font-weight: 700; }}
QLabel[status="error"] {{ color: {t.danger}; font-weight: 700; }}
QLabel[badge="true"] {{ min-height: 24px; padding: 0 8px; border: 1px solid {t.border};
    border-radius: 12px; background: {t.elevated}; color: {t.muted}; }}
QLabel[badge="true"][status="active"] {{ color: {t.accent}; border-color: {t.accent}; background: {t.selection}; }}
QLabel[badge="true"][status="error"] {{ color: {t.danger}; border-color: {t.danger}; }}
QLabel[badge="true"][status="warning"] {{ color: {t.warning}; border-color: {t.warning}; background: {t.warning_surface}; }}
QPushButton {{ min-height: 32px; padding: 0 10px; border-radius: 6px;
    border: 1px solid {t.input_border}; background: {t.surface}; color: {t.text}; }}
QPushButton:hover, QToolButton:hover {{ border-color: {t.accent}; background: {t.selection}; }}
QPushButton:pressed {{ background: {t.elevated}; }}
QPushButton:focus, QToolButton:focus {{ border: 2px solid {t.accent}; }}
QPushButton:disabled, QToolButton:disabled {{ color: {t.disabled_text}; background: {t.disabled_surface}; border-color: {t.border}; }}
QPushButton[primary="true"] {{ background: {t.primary}; color: {t.primary_text}; border-color: {t.primary}; font-weight: 700; }}
QPushButton[danger="true"], QToolButton[danger="true"] {{ color: {t.danger}; border-color: {t.danger}; background: {t.surface}; }}
QPushButton[view="true"] {{ min-height: 28px; padding: 0 10px; }}
QPushButton[compact="true"] {{ min-height: 28px; max-height: 28px; padding: 0 9px; }}
QPushButton[view="true"]:checked {{ background: {t.selection}; color: {t.accent}; border-color: {t.accent}; font-weight: 700; }}
QDialog QPushButton[primary="true"] {{ min-height: 36px; }}
QToolButton {{ min-width: 28px; min-height: 28px; max-width: 28px; max-height: 28px;
    border-radius: 5px; border: 1px solid {t.input_border}; background: {t.surface}; color: {t.text}; }}
QToolButton[wide="true"] {{ max-width: 16777215px; padding: 0 8px; }}
QToolButton:pressed, QToolButton:checked {{ border-color: {t.accent}; background: {t.selection}; }}
QToolButton[calendarNav="true"] {{ min-width: 30px; min-height: 30px; max-width: 30px; max-height: 30px;
    border-radius: 6px; font-size: 16pt; font-weight: 700; }}
QLabel[calendarMonth="true"] {{ font-size: 12pt; font-weight: 700; color: {t.text}; }}
QLabel[calendarWeekday="true"] {{ min-height: 24px; color: {t.muted}; font-weight: 700; }}
QFrame[calendarDay="true"] {{ background: {t.surface}; border: 1px solid {t.border}; border-radius: 5px; }}
QFrame[calendarDay="true"][selected="true"] {{ border: 2px solid {t.accent}; background: {t.selection}; }}
QFrame[calendarDay="true"][outsideMonth="true"] {{ background: {t.background}; }}
QFrame[calendarDay="true"][outsideMonth="true"] QLabel[calendarDate="true"] {{ color: {t.disabled_text}; }}
QLabel[calendarDate="true"] {{ font-weight: 700; color: {t.text}; border: 0; background: transparent; }}
QToolButton[calendarEntry="true"] {{ min-height: 20px; max-height: 20px; max-width: 16777215px;
    padding: 0 4px; border: 1px solid transparent; border-radius: 4px; text-align: left;
    background: {t.selection}; color: {t.text}; font-size: 9pt; }}
QToolButton[calendarEntry="true"][progressState="done"] {{ background: {t.disabled_surface}; color: {t.muted}; }}
QToolButton[calendarEntry="true"][warning="true"] {{ background: {t.warning_surface}; color: {t.warning}; }}
QToolButton[calendarEntry="true"][deadline="true"] {{ border-color: {t.warning}; color: {t.warning}; font-weight: 700; }}
QToolButton[calendarEntry="true"][calendarMore="true"] {{ background: transparent; color: {t.accent}; font-weight: 700; }}
QToolButton[calendarEntry="true"]:hover {{ border-color: {t.accent}; background: {t.selection}; }}
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QDateEdit, QDoubleSpinBox, QSpinBox {{
    min-height: 30px; border: 1px solid {t.input_border}; border-radius: 5px;
    background: {t.surface}; color: {t.text}; padding: 1px 6px; selection-background-color: {t.accent}; }}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QDateEdit:focus,
QDoubleSpinBox:focus, QSpinBox:focus {{ border: 2px solid {t.accent}; }}
QComboBox QAbstractItemView, QMenu {{ background: {t.surface}; color: {t.text}; border: 1px solid {t.border};
    selection-background-color: {t.selection}; selection-color: {t.text}; }}
QTableWidget, QTreeWidget, QListWidget, QCalendarWidget QAbstractItemView {{
    background: {t.surface}; color: {t.text}; border: 1px solid {t.border}; border-radius: 6px;
    gridline-color: {t.border}; alternate-background-color: {t.elevated};
    selection-background-color: {t.selection}; selection-color: {t.text}; }}
QHeaderView::section {{ background: {t.elevated}; color: {t.text}; border: none; border-bottom: 1px solid {t.border};
    padding: 7px 6px; font-weight: 700; }}
QTableWidget::item {{ padding: 4px; }}
QTableWidget::item:selected, QTreeWidget::item:selected {{ background: {t.selection}; color: {t.text}; }}
QTabWidget::pane {{ border: 0; top: -1px; }}
QTabBar::tab {{ padding: 9px 16px; color: {t.muted}; border-bottom: 3px solid transparent; }}
QTabBar::tab:selected {{ color: {t.text}; border-bottom: 3px solid {t.accent}; font-weight: 700; }}
QProgressBar {{ border: 0; border-radius: 5px; background: {t.elevated}; color: {t.text}; text-align: center; min-height: 18px; }}
QProgressBar::chunk {{ border-radius: 5px; background: {t.accent}; }}
QWidget[progressCell="true"] {{ background: transparent; }}
QWidget[progressCell="true"] QProgressBar {{ min-height: 16px; max-height: 16px; }}
QScrollArea {{ border: 0; background: transparent; }}
QScrollBar:vertical {{ background: {t.background}; width: 12px; margin: 0; }}
QScrollBar:horizontal {{ background: {t.background}; height: 12px; margin: 0; }}
QScrollBar::handle {{ background: {t.input_border}; border-radius: 5px; min-height: 24px; min-width: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QCheckBox {{ spacing: 6px; color: {t.text}; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {t.input_border}; border-radius: 3px; background: {t.surface}; }}
QCheckBox::indicator:checked {{ background: {t.accent}; border-color: {t.accent}; }}
QToolTip {{ background: {t.elevated}; color: {t.text}; border: 1px solid {t.border}; padding: 5px; }}
"""


def apply_theme(app: QApplication) -> ThemeManager:
    manager = ThemeManager(app)
    app._intraflow_theme_manager = manager  # type: ignore[attr-defined]
    return manager
