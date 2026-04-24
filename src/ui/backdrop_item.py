from __future__ import annotations

from enum import Enum
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


class _Corner(Enum):
    """Identifier for which corner of a backdrop a resize grip is attached to.

    The mapping is consistent with screen coordinates used by Qt:
    Y grows downward, so "north" is the top edge and "south" the
    bottom.
    """
    NW = "NW"
    NE = "NE"
    SW = "SW"
    SE = "SE"


class BackdropItem(QGraphicsItem):
    """Rectangular frame drawn behind a group of nodes.

    A backdrop is a pure visual affordance: it has no connection to
    the flow model, no execution semantics, and does not appear in the
    node palette. Use it as a "chapter heading" on the canvas —
    e.g. "Colour prep", "Alpha mask" — so dense pipelines stay
    readable.

    Sits on a lower Z than nodes (:attr:`Z_VALUE`) so mouse events on
    the interior of a framed group still reach the node on top. Drag
    the title bar to move; drag *any* of the four corner grips to
    resize — both axes scale at once and the opposite corner stays
    pinned. All four are needed because the bottom-right grip alone
    is unreachable as soon as another node sits on top of it.

    The header carries an X close button on the right edge, mirroring
    the affordance every regular node has.
    """

    Z_VALUE: int = -10
    HEADER_HEIGHT: float = 22.0
    CORNER_RADIUS: float = 6.0
    GRIP_SIZE: float = 12.0
    CLOSE_BUTTON_SIZE: float = 14.0
    CLOSE_BUTTON_MARGIN: float = 4.0
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

        self.setZValue(self.Z_VALUE)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(
            QGraphicsItem.GraphicsItemFlag.ItemSendsScenePositionChanges, True,
        )

        # One grip per corner — bottom-right alone gets buried under
        # nodes too easily to be a reliable handle.
        self._grips: dict[_Corner, _BackdropResizeGrip] = {
            corner: _BackdropResizeGrip(self, corner) for corner in _Corner
        }
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
        """Update the backdrop rectangle. Enforces the minimum so the
        resize grips can't collapse the frame out of existence."""
        new_w = max(MIN_BACKDROP_WIDTH, float(width))
        new_h = max(MIN_BACKDROP_HEIGHT, float(height))
        if (new_w, new_h) == (self._width, self._height):
            return
        self.prepareGeometryChange()
        self._width = new_w
        self._height = new_h
        self._reposition_children()
        self.update()

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
        # The close button paints itself separately so the text doesn't
        # need to know about it; we just leave room on the right.
        if self._title:
            title_rect = QRectF(
                self.TITLE_PADDING,
                0.0,
                self._width
                - 2 * self.TITLE_PADDING
                - self.CLOSE_BUTTON_SIZE
                - self.CLOSE_BUTTON_MARGIN,
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
        """Place every grip + close button at its corner / header slot.

        Called from :meth:`set_size` and from ``__init__``. Each grip
        sits exactly on its corner (top-left coordinate of the
        ``GRIP_SIZE`` square aligns with the corner so the grip extends
        into the frame and not outside it).
        """
        gs = self.GRIP_SIZE
        w = self._width
        h = self._height
        self._grips[_Corner.NW].setPos(0, 0)
        self._grips[_Corner.NE].setPos(w - gs, 0)
        self._grips[_Corner.SW].setPos(0, h - gs)
        self._grips[_Corner.SE].setPos(w - gs, h - gs)

        cb_size = self.CLOSE_BUTTON_SIZE
        cb_margin = self.CLOSE_BUTTON_MARGIN
        self._close_button.setPos(
            w - cb_size - cb_margin,
            (self.HEADER_HEIGHT - cb_size) / 2.0,
        )


class _BackdropResizeGrip(QGraphicsItem):
    """Drag handle attached to one corner of a backdrop.

    Each corner pins the *opposite* corner during a drag, so the
    handle the user grabs is the one that follows the cursor and the
    frame grows / shrinks symmetrically about that anchor. Below the
    minimum size, the frame clamps and the dragged corner stops where
    it would have shrunk past the anchor.
    """

    SIZE: float = 12.0

    _CURSORS: dict[_Corner, Qt.CursorShape] = {
        _Corner.NW: Qt.CursorShape.SizeFDiagCursor,  # top-left  ↘ shape
        _Corner.SE: Qt.CursorShape.SizeFDiagCursor,  # bot-right ↘
        _Corner.NE: Qt.CursorShape.SizeBDiagCursor,  # top-right ↙
        _Corner.SW: Qt.CursorShape.SizeBDiagCursor,  # bot-left  ↙
    }

    def __init__(self, backdrop: BackdropItem, corner: _Corner) -> None:
        super().__init__(parent=backdrop)
        self._backdrop = backdrop
        self._corner = corner
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemStacksBehindParent, False)
        self.setCursor(self._CURSORS[corner])
        self.setZValue(1)
        self._drag_start_scene: QPointF | None = None
        self._drag_start_pos: QPointF | None = None
        self._drag_start_size: tuple[float, float] | None = None

    def boundingRect(self) -> QRectF:  # type: ignore[override]
        return QRectF(0, 0, self.SIZE, self.SIZE)

    def paint(self, painter: QPainter, option, widget=None) -> None:  # type: ignore[override]
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(QColor(200, 200, 200, 180), 1))
        # Three short diagonal tick marks oriented for the corner the
        # grip sits on, so the affordance points "outward" the way an
        # actual resize handle should.
        s = self.SIZE
        if self._corner == _Corner.SE:
            for i in (2, 5, 8):
                painter.drawLine(QPointF(s - i, s - 1), QPointF(s - 1, s - i))
        elif self._corner == _Corner.NW:
            for i in (2, 5, 8):
                painter.drawLine(QPointF(0, i), QPointF(i, 0))
        elif self._corner == _Corner.NE:
            for i in (2, 5, 8):
                painter.drawLine(QPointF(s - i, 0), QPointF(s, i))
        else:  # SW
            for i in (2, 5, 8):
                painter.drawLine(QPointF(0, s - i), QPointF(i, s))

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_scene = event.scenePos()
            self._drag_start_pos = self._backdrop.pos()
            self._drag_start_size = (self._backdrop.width, self._backdrop.height)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if (
            self._drag_start_scene is None
            or self._drag_start_pos is None
            or self._drag_start_size is None
        ):
            super().mouseMoveEvent(event)
            return
        delta = event.scenePos() - self._drag_start_scene
        sp = self._drag_start_pos
        sw, sh = self._drag_start_size

        new_x = sp.x()
        new_y = sp.y()
        new_w = sw
        new_h = sh

        if self._corner in (_Corner.SE, _Corner.NE):
            new_w = sw + delta.x()
        else:  # NW, SW — pull the left edge with the cursor
            new_w = sw - delta.x()
            new_x = sp.x() + delta.x()

        if self._corner in (_Corner.SE, _Corner.SW):
            new_h = sh + delta.y()
        else:  # NW, NE — pull the top edge with the cursor
            new_h = sh - delta.y()
            new_y = sp.y() + delta.y()

        # Clamp to minimum, and when clamped, re-pin the moved edge so
        # the opposite corner doesn't drift.
        if new_w < MIN_BACKDROP_WIDTH:
            if self._corner in (_Corner.NW, _Corner.SW):
                new_x = sp.x() + (sw - MIN_BACKDROP_WIDTH)
            new_w = MIN_BACKDROP_WIDTH
        if new_h < MIN_BACKDROP_HEIGHT:
            if self._corner in (_Corner.NW, _Corner.NE):
                new_y = sp.y() + (sh - MIN_BACKDROP_HEIGHT)
            new_h = MIN_BACKDROP_HEIGHT

        self._backdrop.setPos(new_x, new_y)
        self._backdrop.set_size(new_w, new_h)
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        self._drag_start_scene = None
        self._drag_start_pos = None
        self._drag_start_size = None
        super().mouseReleaseEvent(event)


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
