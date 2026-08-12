from __future__ import annotations

from PySide6.QtCore import QEvent, QSettings, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QStyledItemDelegate,
    QTableView,
    QToolTip,
    QTreeView,
)


class _ElidedTextDelegate(QStyledItemDelegate):
    """Show the complete cell value when the rendered text is elided."""

    def helpEvent(self, event, view, option, index) -> bool:  # type: ignore[override]
        if event and event.type() == QEvent.Type.ToolTip:
            value = index.data(Qt.ItemDataRole.DisplayRole)
            cell_text = "" if value is None else str(value)
            if cell_text and option.fontMetrics.horizontalAdvance(cell_text) > option.rect.width() - 12:
                QToolTip.showText(event.globalPos(), cell_text, view)
                return True
        return super().helpEvent(event, view, option, index)


def configure_columns(
    view: QTableView | QTreeView,
    key: str,
    default_widths: tuple[int, ...],
    *,
    row_height: int = 30,
) -> None:
    """Apply stable, user-resizable columns and persist their workstation state."""

    view.setObjectName(key)
    view.setTextElideMode(Qt.TextElideMode.ElideRight)
    view.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    view.setWordWrap(False)
    view.setItemDelegate(_ElidedTextDelegate(view))

    if isinstance(view, QTableView):
        view.verticalHeader().setDefaultSectionSize(row_height)
        view.verticalHeader().setMinimumSectionSize(row_height)
    else:
        view.setUniformRowHeights(True)

    header = view.header() if isinstance(view, QTreeView) else view.horizontalHeader()
    header.setSectionsMovable(False)
    header.setStretchLastSection(False)
    header.setMinimumSectionSize(48)
    header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

    settings = QSettings(
        QSettings.Format.IniFormat, QSettings.Scope.UserScope, "IGLOO", "IntraFlow",
    )
    state_key = f"table-columns/v1/{key}"
    saved_state = settings.value(state_key)
    restored = bool(saved_state) and header.restoreState(saved_state)
    if not restored:
        for index, width in enumerate(default_widths):
            if index < header.count():
                header.resizeSection(index, width)

    def save_state(*_args) -> None:
        settings.setValue(state_key, header.saveState())
        settings.sync()

    view._save_column_state = save_state  # type: ignore[attr-defined]
    view._column_settings = settings  # type: ignore[attr-defined]
    header.sectionResized.connect(view._save_column_state)  # type: ignore[attr-defined]
