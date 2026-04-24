from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QGraphicsItem

from ui.theme import NODE_BORDER_SELECTED, NODE_TITLE_TEXT_COLOR

if TYPE_CHECKING:
    pass


#: Default fill when a backdrop is first dropped — a subtle, muted
#: amber so the frame reads as a loose grouping affordance without
#: fighting the nodes inside for attention.
DEFAULT_BACKDROP_COLOR: QColor = QColor(70, 60, 40, 140)

#: Default dimensions used when the user drops a fresh backdrop.
DEFAULT_BACKDROP_WIDTH: float = 320.0
DEFAULT_BACKDROP_HEIGHT: float = 220.0

#: Minimum size when the user drags any of the resize grips. Small
#: enough that a backdrop can frame a single node, but not so small
#: it collapses into an invisible square.
MIN_BACKDROP_WIDTH: float = 80.0
MIN_BACKDROP_HEIGHT: float = 60.0

#: Built-in palette offered through the context menu. Kept deliberately
#: small — this is a "hint at intent" affordance, not a full colour
#: picker. Values mirror the muted dark-theme palette so backdrops
#: read as loose grouping rather than as primary UI.
BACKDROP_PRESETS: dict[str, QColor] = {
    "Amber":   QColor( 70,  60,  40, 140),
    "Azure":   QColor( 40,  60,  80, 140),
    "Forest":  QColor( 40,  70,  50, 140),
    "Plum":    QColor( 70,  45,  70, 140),
    "Slate":   QColor( 55,  55,  60, 140),
}


class BackdropItem(QGraphicsItem):
    """Rectangular frame drawn behind a group of nodes.

    A backdrop is a pure visual affordance: it has no connection to
    the flow model, no execution semantics, and does not appear in
    the node palette. Use it as a "chapter heading" on the canvas —
    e.g. "Colour prep", "Alpha mask" — so dense pipelines stay
    readable.

    Sits on a lower Z than nodes (:attr:`Z_VALUE`) so mouse events
    on the interior of a framed group still reach the node on top.
    Drag the title bar to move; the geometry is fixed at creation
    time (see :meth:`FlowScene.create_group_around_selection`) and
    is not interactively resizable — the framed group's contents are
    expected to evolve, not the frame itself.

    The header carries an X close button on the right edge, mirroring
    the affordance every regular node has.
    """

    Z_VALUE: int = -10
    HEADER_HEIGHT: float = 22.0
    CORNER_RADIUS: float = 6.0
    CLOSE_BUTTON_SIZE: float = 14.0
    HEADER_BUTTON_MARGIN: float = 4.0
    TITLE_PADDING: float = 8.0

    def __init__(
        self,
        title: str = "Backdrop",
        width: float = DEFAULT_BACKDROP_WIDTH,
        height: float = DEFAULT_BACKDROP_HEIGHT,
        color: QColor | None = None,
    ) -> None:
        super().__init__()
        self._title: str = title
        self._width: float = float(width)
        self._height: float = float(height)
        self._color: QColor = QColor(color if color is not None else DEFAULT_BACKDROP_COLOR)
        # Drag bookkeeping: when the user starts dragging the
        # backdrop, we snapshot every node fully inside the frame at
        # press-time and shift them by the same delta on every
        # position change. The snapshot is *not* re-evaluated
        # mid-drag, so a node that wasn't framed at press-time won't
        # be swept along just because the moving backdrop crossed it.
        # Capture-the-enclosed is always on — the typical creation
        # path is "Create Group" around an existing selection, so by
        # the time the user moves the backdrop, it already frames
        # exactly what they want to drag together.
        self._captured_snapshot: list = []
        self._drag_anchor_pos: QPointF | None = None

        self.setZValue(self.Z_VALUE)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(
            QGraphicsItem.GraphicsItemFlag.ItemSendsScenePositionChanges, True,
        )

        self._close_button = _BackdropCloseButton(self)
        self._reposition_children()

    # ── Public API ─────────────────────────────────────────────────────────────

    @property
    def title(self) -> str:
        return self._title

    def set_title(self, title: str) -> None:
        self._title = str(title)
        self.update()

    @property
    def color(self) -> QColor:
        return QColor(self._color)

    def set_color(self, color: QColor) -> None:
        self._color = QColor(color)
        self.update()

    @property
    def width(self) -> float:
        return self._width

    @property
    def height(self) -> float:
        return self._height

    def set_size(self, width: float, height: float) -> None:
        """Update the backdrop rectangle. Used by the loader and
        :meth:`FlowScene.create_group_around_selection` — the user
        can't drive this at runtime since the frame has no resize
        handles. The minimum clamp is kept as defensive sanity for
        legacy flow files.
        """
        new_w = max(MIN_BACKDROP_WIDTH, float(width))
        new_h = max(MIN_BACKDROP_HEIGHT, float(height))
        if (new_w, new_h) == (self._width, self._height):
            return
        self.prepareGeometryChange()
        self._width = new_w
        self._height = new_h
        self._reposition_children()
        self.update()

    # ── Capture / drag-with-contents ───────────────────────────────────────────

    def captured_node_items(self) -> list:
        """Return every node-item *fully* enclosed by this backdrop.

        "Fully enclosed" means the node's scene-bounding rect is
        completely inside the backdrop's scene-bounding rect — partial
        overlap doesn't count, so a node only "joins" the backdrop's
        group once the user has clearly placed it inside.

        Imported lazily to avoid pulling :mod:`ui.node_item` (which
        wires up Qt widgets and the param-widget infrastructure) into
        backdrop tests that only care about geometry.
        """
        if self.scene() is None:
            return []
        from ui.node_item import NodeItem

        backdrop_rect = self.sceneBoundingRect()
        captured = []
        for item in self.scene().items():
            if isinstance(item, NodeItem) and backdrop_rect.contains(
                item.sceneBoundingRect()
            ):
                captured.append(item)
        return captured

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        # Snapshot the framed nodes + their current positions so the
        # move handler can shift them by the same delta the backdrop
        # travels. Taken *before* super() starts the drag so
        # press-time geometry is what we lock in.
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_anchor_pos = self.scenePos()
            self._captured_snapshot = [
                (item, item.pos()) for item in self.captured_node_items()
            ]
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        self._drag_anchor_pos = None
        self._captured_snapshot = []
        super().mouseReleaseEvent(event)

    def itemChange(self, change, value):  # type: ignore[override]
        if (
            change == QGraphicsItem.GraphicsItemChange.ItemScenePositionHasChanged
            and self._drag_anchor_pos is not None
            and self._captured_snapshot
        ):
            delta = self.scenePos() - self._drag_anchor_pos
            for node_item, start_pos in self._captured_snapshot:
                node_item.setPos(start_pos + delta)
        return super().itemChange(change, value)

    # ── Qt overrides ───────────────────────────────────────────────────────────

    def boundingRect(self) -> QRectF:  # type: ignore[override]
        return QRectF(0, 0, self._width, self._height)

    def paint(self, painter: QPainter, option, widget=None) -> None:  # type: ignore[override]
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Body
        body_path = QPainterPath()
        body_path.addRoundedRect(
            self.boundingRect(), self.CORNER_RADIUS, self.CORNER_RADIUS,
        )
        painter.fillPath(body_path, QBrush(self._color))

        # Border: amber when selected, subtle darker tint otherwise.
        if self.isSelected():
            painter.setPen(QPen(NODE_BORDER_SELECTED, 1.5))
        else:
            border = QColor(self._color)
            border.setAlpha(230)
            border.setRed(max(0, border.red() - 25))
            border.setGreen(max(0, border.green() - 25))
            border.setBlue(max(0, border.blue() - 25))
            painter.setPen(QPen(border, 1.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(body_path)

        # Title bar text — rendered directly onto the header strip.
        # The close button paints itself separately, so we just leave
        # room on the right for it.
        if self._title:
            title_rect = QRectF(
                self.TITLE_PADDING,
                0.0,
                self._width
                - 2 * self.TITLE_PADDING
                - self.CLOSE_BUTTON_SIZE
                - self.HEADER_BUTTON_MARGIN,
                self.HEADER_HEIGHT,
            )
            font = QFont(painter.font())
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor(230, 230, 230))
            painter.drawText(
                title_rect,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                self._title,
            )

    # ── Internals ──────────────────────────────────────────────────────────────

    def _reposition_children(self) -> None:
        """Place the close button in its header slot.

        Called from :meth:`set_size` and from ``__init__``.
        """
        cb_size = self.CLOSE_BUTTON_SIZE
        margin = self.HEADER_BUTTON_MARGIN
        self._close_button.setPos(
            self._width - cb_size - margin,
            (self.HEADER_HEIGHT - cb_size) / 2.0,
        )


class _BackdropCloseButton(QGraphicsItem):
    """``X`` button at the top-right of a backdrop's header.

    Clicking it asks the owning scene to remove the backdrop, mirroring
    the close affordance every regular node header carries.
    """

    SIZE: float = 14.0
    Z_VALUE: int = 2

    def __init__(self, backdrop: BackdropItem) -> None:
        super().__init__(parent=backdrop)
        self._backdrop = backdrop
        self._hovered = False
        self._pressed = False
        self.setZValue(self.Z_VALUE)
        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def boundingRect(self) -> QRectF:  # type: ignore[override]
        return QRectF(0, 0, self.SIZE, self.SIZE)

    def paint(self, painter: QPainter, option, widget=None) -> None:  # type: ignore[override]
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if self._hovered or self._pressed:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor(255, 255, 255, 70)))
            painter.drawRoundedRect(self.boundingRect(), 2, 2)
        pen = QPen(NODE_TITLE_TEXT_COLOR, 1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        m = 4.0
        s = self.SIZE
        painter.drawLine(QPointF(m, m), QPointF(s - m, s - m))
        painter.drawLine(QPointF(s - m, m), QPointF(m, s - m))

    def hoverEnterEvent(self, event) -> None:  # type: ignore[override]
        self._hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event) -> None:  # type: ignore[override]
        self._hovered = False
        self.update()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self._pressed = True
            self.update()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton and self._pressed:
            self._pressed = False
            self.update()
            if self.boundingRect().contains(event.pos()):
                scene = self.scene()
                backdrop = self._backdrop
                if scene is not None and hasattr(scene, "remove_backdrop"):
                    # Defer so we don't delete ourselves from inside
                    # our own event handler.
                    QTimer.singleShot(0, lambda: scene.remove_backdrop(backdrop))
            event.accept()
            return
        super().mouseReleaseEvent(event)
