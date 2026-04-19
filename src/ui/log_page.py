from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QVBoxLayout,
    QWidget,
)

from ui.icons import material_icon
from typing_extensions import override

from ui.page import PageBase, ToolbarSection

if TYPE_CHECKING:
    pass


class LogPage(PageBase):
    """Page for displaying the log file
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        root = QVBoxLayout(self)
        root.setContentsMargins(40, 60, 40, 40)
        root.setSpacing(12)


    # ── Page hooks ─────────────────────────────────────────────────────────────

    def page_title(self) -> str:
        return ""  # MainWindow shows the bare app name on the start page

    @override
    def page_selector_label(self) -> str:
        return "Log"

    @override
    def page_selector_icon(self) -> QIcon:
        return material_icon("home")

    def page_toolbar_sections(self) -> list[ToolbarSection]:
        return []

    def on_activated(self) -> None:
        pass


