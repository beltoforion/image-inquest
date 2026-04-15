from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget

if TYPE_CHECKING:
    from PySide6.QtGui import QAction, QIcon
    from PySide6.QtWidgets import QMenu


class Page(QWidget):
    """Base class for every top-level page stacked inside MainWindow.

    A page owns a QWidget body (populated by the subclass) and optionally
    a list of QMenus that the host main-window installs on the global
    menu bar while the page is active, and removes when the page is
    deactivated.

    The :attr:`title_changed` signal lets a page request that the main
    window update the window title without knowing about the main window
    directly.

    Subclasses should:

    * build their widgets in ``__init__`` via a normal layout call,
    * return their per-page menus from :meth:`page_menus`,
    * return their per-page toolbar actions from :meth:`page_actions`,
    * emit :attr:`title_changed` whenever their context (e.g. current
      flow name) changes.
    """

    title_changed = Signal(str)

    def page_menus(self) -> list[QMenu]:
        """Return the menus this page contributes to the global menu bar.

        Default: empty. Override to attach Save/Run/etc. to the
        application menu bar while the page is active.
        """
        return []

    def page_actions(self) -> list[QAction]:
        """Toolbar actions the page contributes.

        MainWindow installs these on the global toolbar, immediately
        after the page-selector buttons, while the page is active.
        Default: empty.
        """
        return []

    def page_label(self) -> str:
        """Stable short label used by the page-selector toolbar button.

        Distinct from :meth:`page_title` (which may include dynamic state
        like the current flow name); this one is used for the toolbar
        button and never changes.
        """
        return type(self).__name__

    def page_icon(self) -> QIcon | None:
        """Optional icon for the page-selector toolbar button."""
        return None

    def page_title(self) -> str:
        """Human-readable page title used in the window caption."""
        return ""

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def on_activated(self) -> None:
        """Called by MainWindow immediately after the page is made visible."""

    def on_deactivated(self) -> None:
        """Called by MainWindow just before another page becomes visible."""
