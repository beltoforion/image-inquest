from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QMenuBar
from PyQt6.QtGui import QFont

from core.flow import Flow
from ui.page import Page

if TYPE_CHECKING:
    from ui.page_manager import PageManager


class StartPage(Page):
    name = "start"

    def __init__(self, menu_bar: QMenuBar, page_manager: PageManager) -> None:
        super().__init__(menu_bar=menu_bar, page_manager=page_manager)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 60, 20, 20)

        title = QLabel("Image Inquest")
        font = QFont()
        font.setPointSize(18)
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)

        layout.addSpacing(20)

        btn_row = QHBoxLayout()
        new_btn = QPushButton("New Flow")
        new_btn.clicked.connect(self._on_new_flow_clicked)
        load_btn = QPushButton("Load Flow")
        load_btn.clicked.connect(self._on_load_flow_clicked)
        btn_row.addWidget(new_btn)
        btn_row.addWidget(load_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        layout.addStretch()

    def _install_menus(self) -> None:
        pass

    def _on_new_flow_clicked(self) -> None:
        self._page_manager.editor_page.set_flow(Flow())
        self._page_manager.activate(self._page_manager.editor_page)

    def _on_load_flow_clicked(self) -> None:
        # TODO: implement flow loading (file dialog + deserialization).
        print("Load Flow: not implemented yet")
