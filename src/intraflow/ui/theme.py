from __future__ import annotations

from PySide6.QtWidgets import QApplication


IGLOO_BLACK = "#000000"
IGLOO_GRAY = "#8A8D8F"
IGLOO_GREEN = "#00A98E"
PRIMARY_GREEN = "#006B5B"
APP_BACKGROUND = "#F4F6F6"
SURFACE = "#FFFFFF"
BORDER = "#D9DEDE"
WARNING = "#B66A00"
DANGER = "#B42318"


STYLE_SHEET = f"""
QWidget {{
    color: #171A1A;
    font-family: "Malgun Gothic", "Segoe UI";
    font-size: 10pt;
}}
QMainWindow, QWidget#appRoot {{ background: {APP_BACKGROUND}; }}
QWidget[card="true"] {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}
QLabel[role="title"] {{ font-size: 17pt; font-weight: 700; color: {IGLOO_BLACK}; }}
QLabel[role="section"] {{ font-size: 12pt; font-weight: 700; color: {IGLOO_BLACK}; }}
QLabel[role="muted"] {{ color: #687071; }}
QLabel[status="active"] {{ color: {PRIMARY_GREEN}; font-weight: 700; }}
QLabel[status="warning"] {{ color: {WARNING}; font-weight: 700; }}
QLabel[status="error"] {{ color: {DANGER}; font-weight: 700; }}
QPushButton {{
    min-height: 36px; padding: 0 14px; border-radius: 6px;
    border: 1px solid #BBC4C3; background: {SURFACE}; color: #202424;
}}
QPushButton:hover {{ border-color: {IGLOO_GREEN}; background: #F0FAF8; }}
QPushButton:disabled {{ color: #A0A7A7; background: #F0F2F2; border-color: #E0E4E4; }}
QPushButton[primary="true"] {{ background: {PRIMARY_GREEN}; color: white; border-color: {PRIMARY_GREEN}; font-weight: 700; }}
QPushButton[primary="true"]:hover {{ background: #00594C; }}
QPushButton[danger="true"] {{ color: {DANGER}; border-color: #FDA29B; background: #FFF6F5; }}
QLineEdit, QTextEdit, QComboBox, QDateEdit, QDoubleSpinBox, QSpinBox {{
    min-height: 32px; border: 1px solid #BBC4C3; border-radius: 5px;
    background: white; padding: 2px 7px; selection-background-color: {IGLOO_GREEN};
}}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QDateEdit:focus,
QDoubleSpinBox:focus, QSpinBox:focus {{ border: 2px solid {IGLOO_GREEN}; }}
QTableWidget, QTreeWidget {{
    background: white; border: 1px solid {BORDER}; border-radius: 6px;
    gridline-color: #E8EBEB; alternate-background-color: #FAFBFB;
    selection-background-color: #DDF4EF; selection-color: #111414;
}}
QHeaderView::section {{
    background: #EEF1F1; color: #3D4444; border: none; border-bottom: 1px solid {BORDER};
    padding: 9px 7px; font-weight: 700;
}}
QTableWidget::item {{ padding: 6px; }}
QTableWidget::item:selected, QTreeWidget::item:selected {{ border-left: 3px solid {IGLOO_GREEN}; }}
QTabWidget::pane {{ border: 0; top: -1px; }}
QTabBar::tab {{ padding: 11px 18px; color: #5F6767; border-bottom: 3px solid transparent; }}
QTabBar::tab:selected {{ color: {IGLOO_BLACK}; border-bottom: 3px solid {IGLOO_GREEN}; font-weight: 700; }}
QProgressBar {{ border: 0; border-radius: 5px; background: #E4E8E8; text-align: center; min-height: 20px; }}
QProgressBar::chunk {{ border-radius: 5px; background: {IGLOO_GREEN}; }}
QToolTip {{ background: #202424; color: white; border: 0; padding: 5px; }}
"""


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE_SHEET)
