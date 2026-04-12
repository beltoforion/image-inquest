from __future__ import annotations

from typing import TYPE_CHECKING, cast

from PyQt6.QtWidgets import QStackedWidget, QMenuBar

from ui.page import Page

if TYPE_CHECKING:
    from ui.node_editor_page import NodeEditorPage
    from ui.start_page import StartPage


class PageManager:
    """Owns all pages and guarantees that only one is active at a time.

    Pages are added to a QStackedWidget so Qt handles their visibility.
    activate() additionally calls the page's activate()/deactivate() hooks
    so each page can install or remove its menu bar entries.
    """

    def __init__(self, stack: QStackedWidget, menu_bar: QMenuBar) -> None:
        self._stack: QStackedWidget = stack
        self._menu_bar: QMenuBar = menu_bar
        self._pages: dict[str, Page] = {}
        self._active: Page | None = None

    def register(self, page: Page) -> None:
        if page.name in self._pages:
            raise ValueError(f"Page '{page.name}' is already registered")
        self._pages[page.name] = page
        self._stack.addWidget(page)

    def activate(self, page: Page) -> None:
        if page.name not in self._pages:
            raise KeyError(f"Page '{page.name}' is not registered")
        if self._active is page:
            return
        if self._active is not None:
            self._active.deactivate()
        self._stack.setCurrentWidget(page)
        page.activate()
        self._active = page

    @property
    def start_page(self) -> StartPage:
        from ui.start_page import StartPage
        return cast("StartPage", self._pages[StartPage.name])

    @property
    def editor_page(self) -> NodeEditorPage:
        from ui.node_editor_page import NodeEditorPage
        return cast("NodeEditorPage", self._pages[NodeEditorPage.name])
