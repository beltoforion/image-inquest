from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QWidget, QMenuBar, QMenu

if TYPE_CHECKING:
    from ui.page_manager import PageManager


class Page(QWidget):
    """Abstract base class for a top-level application page.

    A Page is a QWidget whose visibility is managed by PageManager via a
    QStackedWidget.  Each page also owns a set of QMenu objects that are
    added to the application menu bar on activation and removed on
    deactivation, so only the active page's menus are visible.

    Subclasses must define:
        name             - unique string identifier used by PageManager.
        _build_ui()      - build and lay out child widgets using self as root.
        _install_menus() - add any page-specific QMenu objects to
                           self._menu_bar and append them to self._menus so
                           the base class can remove them on deactivation.
    """

    name: str

    def __init__(self, menu_bar: QMenuBar, page_manager: PageManager) -> None:
        super().__init__()
        self._menu_bar: QMenuBar = menu_bar
        self._page_manager: PageManager = page_manager
        self._menus: list[QMenu] = []
        self._active: bool = False
        self._build_ui()

    def _build_ui(self) -> None:
        raise NotImplementedError

    def _install_menus(self) -> None:
        raise NotImplementedError

    @property
    def is_active(self) -> bool:
        return self._active

    def activate(self) -> None:
        if self._active:
            return
        self._install_menus()
        self._active = True

    def deactivate(self) -> None:
        if not self._active:
            return
        for menu in self._menus:
            self._menu_bar.removeAction(menu.menuAction())
        self._menus.clear()
        self._active = False
