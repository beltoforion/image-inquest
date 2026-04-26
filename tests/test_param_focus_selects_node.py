"""Tests for the focus ↔ selection coupling on a NodeItem (issue #170).

Two contracts are exercised:

* **Focus → selection.** When a param widget on a node body gains
  keyboard focus, the owning ``NodeItem`` becomes the only selected
  item — even if focus arrives via code (``QWidget.setFocus``) rather
  than a physical mouse click, since both go through the same
  ``QEvent.FocusIn`` path.

* **Deselection → focus drop.** When a node loses selection, every
  embedded param widget on it that currently holds keyboard focus
  must drop it, so the next keystroke doesn't edit a control whose
  owning node is no longer "active".

Headless Qt: ``QT_QPA_PLATFORM=offscreen`` is set before PySide6
imports, mirroring the rest of the UI test suite.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Headless Qt: must be set before PySide6 is imported anywhere.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QFocusEvent
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsProxyWidget,
    QGraphicsView,
    QWidget,
)

from core.flow import Flow
from nodes.filters.overlay import Overlay
from ui.flow_scene import FlowScene
from ui.node_item import NodeItem


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication(sys.argv)


def _scene_with_two_nodes(qapp: QApplication) -> tuple[FlowScene, NodeItem, NodeItem]:
    """Two Overlay nodes on a fresh scene — Overlay has several
    param-style ports (angle / scale / xpos / ypos / alpha) so we
    have something focusable to drive the tests with."""
    scene = FlowScene()
    scene.set_flow(Flow(name="focus_test"))
    a = scene.add_node(Overlay(), QPointF(0, 0))
    b = scene.add_node(Overlay(), QPointF(300, 0))
    return scene, a, b


def _first_focusable_inner(node_item: NodeItem) -> QWidget:
    """Return the first focusable child widget hosted inside any of
    *node_item*'s param widgets — that's what actually receives
    keyboard focus when the user clicks a spinbox / line-edit /
    combo, not the wrapper."""
    for proxy in node_item._param_proxies_by_row.values():
        wrapper = proxy.widget()
        if wrapper is None:
            continue
        for child in wrapper.findChildren(QWidget):
            if child.focusPolicy() != Qt.FocusPolicy.NoFocus:
                return child
        return wrapper
    raise RuntimeError("Overlay node has no param widgets to focus on")


def _send_focus_in(widget: QWidget) -> None:
    """Synthesise the ``QEvent.FocusIn`` a real click would produce.

    ``QWidget.setFocus()`` is a no-op when the widget isn't part of a
    realised, active window — which is the case for proxy-hosted
    widgets in an offscreen-platform test that doesn't show a
    :class:`QGraphicsView`. Sending the event directly tests exactly
    what the production filter listens for and keeps the test
    independent of Qt's screen / window-activation plumbing.
    """
    event = QFocusEvent(QEvent.Type.FocusIn, Qt.FocusReason.MouseFocusReason)
    QApplication.sendEvent(widget, event)


def _send_focus_out(widget: QWidget) -> None:
    event = QFocusEvent(QEvent.Type.FocusOut, Qt.FocusReason.MouseFocusReason)
    QApplication.sendEvent(widget, event)


def test_focus_in_param_widget_selects_owner_node(qapp: QApplication) -> None:
    """A FocusIn on a param widget belonging to node B → B becomes
    the only selected node, even though A was selected before."""
    scene, a, b = _scene_with_two_nodes(qapp)
    a.setSelected(True)
    assert a.isSelected() and not b.isSelected()

    _send_focus_in(_first_focusable_inner(b))
    qapp.processEvents()

    assert b.isSelected(), "focusing B's param widget must select B"
    assert not a.isSelected(), "previous selection must be cleared"


def test_focus_in_widget_on_already_selected_node_is_noop(qapp: QApplication) -> None:
    """Selecting the same node again would be wasteful (it would
    fire `selectionChanged` and re-trigger every panel update). The
    filter must short-circuit when the node is already selected."""
    scene, a, _ = _scene_with_two_nodes(qapp)
    a.setSelected(True)
    selection_events: list[None] = []
    scene.selectionChanged.connect(lambda: selection_events.append(None))

    _send_focus_in(_first_focusable_inner(a))
    qapp.processEvents()

    assert a.isSelected()
    assert selection_events == [], (
        "no selectionChanged should fire when the focused widget is "
        "already on the selected node"
    )


def test_focus_collapses_multi_selection_to_single_owner(qapp: QApplication) -> None:
    """When several nodes are selected at once and the user clicks
    into a widget on one of them, focus is single-target — the
    selection must collapse to that one node so the panels don't
    show stale multi-selection state."""
    scene, a, b = _scene_with_two_nodes(qapp)
    a.setSelected(True)
    b.setSelected(True)
    assert a.isSelected() and b.isSelected()

    _send_focus_in(_first_focusable_inner(b))
    qapp.processEvents()

    assert b.isSelected()
    assert not a.isSelected()


def test_unselecting_node_clears_param_widget_focus(qapp: QApplication) -> None:
    """Inverse direction: when the user moves selection to another
    node (or clicks on the canvas background), any param widget on
    the previously-selected node that still holds keyboard focus
    must lose it.

    Uses a real :class:`QGraphicsView` so the embedded widget can
    hold actual keyboard focus — proxy-hosted widgets in a sceneless
    scene can't, even with the offscreen Qt platform."""
    scene, a, b = _scene_with_two_nodes(qapp)
    view = QGraphicsView(scene)
    view.show()
    qapp.processEvents()

    inner = _first_focusable_inner(a)
    inner.setFocus()
    qapp.processEvents()
    assert inner.hasFocus(), "test precondition — widget must hold real focus"
    a.setSelected(True)
    qapp.processEvents()
    assert a.isSelected()

    # Move selection to B by code (the user would click B's body).
    a.setSelected(False)
    b.setSelected(True)
    qapp.processEvents()

    assert not inner.hasFocus(), (
        "param widget on the now-unselected node must lose focus"
    )
    assert b.isSelected() and not a.isSelected()


def test_clearing_all_selection_clears_param_widget_focus(qapp: QApplication) -> None:
    """Clicking on empty canvas clears the whole selection — every
    param widget that had focus must drop it too."""
    scene, a, _ = _scene_with_two_nodes(qapp)
    view = QGraphicsView(scene)
    view.show()
    qapp.processEvents()

    inner = _first_focusable_inner(a)
    inner.setFocus()
    a.setSelected(True)
    qapp.processEvents()
    assert inner.hasFocus() and a.isSelected()

    scene.clearSelection()
    qapp.processEvents()

    assert not inner.hasFocus()
