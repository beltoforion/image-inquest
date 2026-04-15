from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import (
    QMainWindow,
    QMenu,
    QMenuBar,
    QStackedWidget,
    QToolBar,
    QToolButton,
)

from constants import APP_NAME, BUILTIN_NODES_DIR, USER_NODES_DIR
from core.flow import Flow
from core.node_registry import NodeRegistry
from ui.node_editor_page import NodeEditorPage
from ui.page import Page
from ui.start_page import StartPage

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Top-level window. Hosts the page stack and the global menu bar.

    MainWindow is the only place that knows about all pages. Each page
    contributes its own menus via :meth:`Page.page_menus`; MainWindow
    clears and re-installs them on every page switch.
    """

    def __init__(self, initial_flow_path: Path | None = None) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)

        # ── Node registry ──
        self._registry = NodeRegistry()
        for err in self._registry.scan_builtin(BUILTIN_NODES_DIR):
            logger.warning("Built-in node scan: %s", err)
        for err in self._registry.scan_user(USER_NODES_DIR):
            logger.warning("User node scan: %s", err)
        logger.info("Registry: %d node(s) loaded", len(self._registry))

        # ── Page stack ──
        self._pages = QStackedWidget()
        self.setCentralWidget(self._pages)

        self._start_page  = StartPage()
        self._editor_page = NodeEditorPage(self._registry)

        self._pages.addWidget(self._start_page)
        self._pages.addWidget(self._editor_page)

        # Wire page signals.
        self._start_page.create_flow_requested.connect(self._on_create_flow)
        self._start_page.open_flow_requested.connect(self._on_open_flow_from_start)
        for page in (self._start_page, self._editor_page):
            page.title_changed.connect(self._update_window_title)

        # ── Menu bar ──
        self._menu_bar: QMenuBar = self.menuBar()
        self._app_menu = self._build_app_menu()
        self._installed_page_menus: list[QMenu] = []

        # ── Toolbar ──
        # A single global toolbar: page-selector radio group on the left,
        # then the active page's own actions. Built once; the page-action
        # tail is rebuilt on every page switch.
        self._pages_in_order: list[Page] = [self._start_page, self._editor_page]
        self._page_to_selector: dict[Page, QAction] = {}
        self._installed_page_actions: list[QAction] = []
        self._page_action_separator: QAction | None = None
        self._toolbar = self._build_toolbar()
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self._toolbar)

        self._activate_page(self._start_page)

        # If a flow was supplied on the command line, jump straight into
        # the editor. Failure falls through to the start page (already
        # active) so a bad CLI arg never blocks app launch.
        if initial_flow_path is not None:
            if self._editor_page.load_flow(initial_flow_path):
                self._activate_page(self._editor_page)
            else:
                logger.warning(
                    "Could not load initial flow %s; staying on start page",
                    initial_flow_path,
                )

    # ── Page switching ─────────────────────────────────────────────────────────

    def _activate_page(self, page: Page) -> None:
        # No-op when already on that page; otherwise we'd churn menus
        # and re-emit on_activated for nothing.
        current = self._pages.currentWidget()
        if current is page:
            self._sync_page_selector(page)
            return

        # Deactivate current.
        if isinstance(current, Page):
            current.on_deactivated()

        # Swap.
        self._pages.setCurrentWidget(page)
        self._install_page_menus(page)
        self._install_page_actions(page)
        self._sync_page_selector(page)
        self._update_window_title(page.page_title())
        page.on_activated()

    def _install_page_menus(self, page: Page) -> None:
        # Remove previously-installed page menus. The app menu is persistent.
        for menu in self._installed_page_menus:
            self._menu_bar.removeAction(menu.menuAction())
            menu.deleteLater()
        self._installed_page_menus = []

        # Install the new page's menus. Do NOT call ``menu.setParent(menu_bar)``
        # — QMenuBar manages menus by their menuAction() and giving the QMenu
        # the menubar as its Qt parent corrupts popup handling and crashes on
        # first open. Holding a Python reference in ``_installed_page_menus``
        # keeps the menu alive for as long as it is attached.
        for menu in page.page_menus():
            self._menu_bar.addMenu(menu)
            self._installed_page_menus.append(menu)

    # ── Toolbar ────────────────────────────────────────────────────────────────

    # Visual size shared by every toolbar button so the radio-style page
    # selector and the page-specific actions all line up the same height.
    _TOOLBAR_ICON_SIZE = QSize(20, 20)
    _TOOLBAR_BUTTON_MIN_WIDTH = 110

    def _build_toolbar(self) -> QToolBar:
        tb = QToolBar("Main", self)
        tb.setObjectName("MainToolbar")
        tb.setMovable(False)
        tb.setIconSize(self._TOOLBAR_ICON_SIZE)
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)

        # Page-selector group: checkable, exclusive (radio behaviour).
        group = QActionGroup(self)
        group.setExclusive(True)
        for page in self._pages_in_order:
            action = QAction(page.page_label(), self)
            action.setCheckable(True)
            icon = page.page_icon()
            if icon is not None:
                action.setIcon(icon)
            # `triggered` only fires when the user activates the button;
            # an exclusive group never re-triggers an already-checked
            # action, so guard against re-activating the same page anyway.
            action.triggered.connect(lambda _checked, p=page: self._activate_page(p))
            group.addAction(action)
            tb.addAction(action)
            self._page_to_selector[page] = action
            self._enforce_button_size(tb, action)

        # Separator before page-specific actions; recreated empty on each
        # page switch through addAction calls below.
        self._page_action_separator = tb.addSeparator()
        return tb

    def _install_page_actions(self, page: Page) -> None:
        # Drop the previous page's actions but leave the page-selector
        # group and the separator in place.
        for action in self._installed_page_actions:
            self._toolbar.removeAction(action)
        self._installed_page_actions = []

        for action in page.page_actions():
            self._toolbar.addAction(action)
            self._installed_page_actions.append(action)
            self._enforce_button_size(self._toolbar, action)

        # Hide the trailing separator when the active page contributes
        # no actions, so we don't render a stray divider at the end.
        if self._page_action_separator is not None:
            self._page_action_separator.setVisible(bool(self._installed_page_actions))

    def _sync_page_selector(self, page: Page) -> None:
        action = self._page_to_selector.get(page)
        if action is not None and not action.isChecked():
            action.setChecked(True)

    def _enforce_button_size(self, tb: QToolBar, action: QAction) -> None:
        button = tb.widgetForAction(action)
        if isinstance(button, QToolButton):
            button.setMinimumWidth(self._TOOLBAR_BUTTON_MIN_WIDTH)

    # ── Menus ──────────────────────────────────────────────────────────────────

    def _build_app_menu(self) -> QMenu:
        """Always-visible application menu (Quit, About)."""
        menu = self._menu_bar.addMenu("&File")

        quit_action = QAction("&Quit", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        menu.addAction(quit_action)

        return menu

    # ── Navigation callbacks ───────────────────────────────────────────────────

    def _on_create_flow(self, name: str) -> None:
        flow = Flow(name=name)
        self._editor_page.set_flow(flow)
        self._activate_page(self._editor_page)

    def _on_open_flow_from_start(self, path: Path) -> None:
        ok = self._editor_page.load_flow(path)
        if ok:
            self._activate_page(self._editor_page)
        # On failure stay on the start page (status label won't help there
        # today; a follow-up could surface the error via QMessageBox).

    def _update_window_title(self, page_title: str) -> None:
        if page_title:
            self.setWindowTitle(f"{APP_NAME} — {page_title}")
        else:
            self.setWindowTitle(APP_NAME)
