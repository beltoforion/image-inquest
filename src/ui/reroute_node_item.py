from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QPainter, QPen
from PySide6.QtWidgets import QGraphicsItem

from ui.node_item import NodeItem, _NodeSignals
from ui.port_item import PortItem
from ui.theme import LINK_COLOR, NODE_BORDER_SELECTED

if TYPE_CHECKING:
    from core.node_base import NodeBase


class RerouteNodeItem(NodeItem):
    """Tiny pass-through dot used to bend a link around other nodes.

    Inherits from :class:`NodeItem` so that every ``isinstance`` check
    in the scene, selection handler and serialiser keeps working, but
    replaces the heavyweight ``__init__`` with a minimal one: no
    header, no params widget, no close/skip/resize buttons. The item
    is simply a small draggable circle that carries one input and one
    output :class:`PortItem`, both centred on the dot so links appear
    to pass straight through.

    Visual: ~10 px circle in the standard link colour, with a thicker
    amber outline when selected — same affordance as a selected link.
    """

    #: Radius of the visible dot.
    RADIUS: float = 5.0
    #: Forgiving hit-box radius — slightly larger than the dot so the
    #: user doesn't need pixel-perfect aim to pick a reroute up.
    HIT_RADIUS: float = 8.0

    def __init__(self, node: NodeBase) -> None:
        # Deliberately skip NodeItem.__init__ — its full header / params /
        # buttons setup is exactly what a reroute is meant to avoid. Go
        # straight to QGraphicsItem so the base Qt state is initialised
        # and then hand-set only the attributes the rest of the code
        # (flow_scene, flow_io, link_item) reads off a node item.
        QGraphicsItem.__init__(self)
        self._node = node
        self._signals = _NodeSignals()
        self._input_ports: list[PortItem] = []
        self._output_ports: list[PortItem] = []
        # NodeItem consumers read these to lay out resize handles and
        # serialise user-set geometry. A reroute has no resizable body,
        # so they're fixed at the dot's diameter and never change.
        self._width: float = 2 * self.RADIUS
        self._body_height: float = 2 * self.RADIUS
        self._user_width: float | None = None
        self._user_height: float | None = None

        self.setZValue(NodeItem.Z_VALUE)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(
            QGraphicsItem.GraphicsItemFlag.ItemSendsScenePositionChanges, True,
        )
        self.setAcceptHoverEvents(False)

        # Both ports sit at the dot's centre so links appear to pass
        # through it without a visible kink. The PortItem constructor
        # already parents to this item, so they'll move with the dot.
        in_port = PortItem(self, "input", 0, node.inputs[0])
        out_port = PortItem(self, "output", 0, node.outputs[0])
        in_port.setPos(0, 0)
        out_port.setPos(0, 0)
        self._input_ports.append(in_port)
        self._output_ports.append(out_port)

    # ── NodeItem API (minimal overrides) ───────────────────────────────────────

    @property
    def is_reroute(self) -> bool:
        """True — used by :class:`~ui.link_item.LinkItem` to pick
        free-tangent bezier routing instead of the default horizontal
        one."""
        return True

    @property
    def body_height(self) -> float:  # type: ignore[override]
        return self._body_height

    @property
    def width(self) -> float:  # type: ignore[override]
        return self._width

    @property
    def user_size(self) -> tuple[float | None, float | None]:  # type: ignore[override]
        # Reroutes don't persist a user size — they're always the
        # built-in dot. Returning (None, None) tells flow_io not to
        # emit a "size" entry for this node on save.
        return (None, None)

    def apply_user_size(self, width: float, height: float) -> None:  # type: ignore[override]
        # Older flows might carry a "size" entry from an accidental
        # save; ignore it rather than resizing the dot.
        return

    def refresh_all_links(self) -> None:  # type: ignore[override]
        for port in (*self._input_ports, *self._output_ports):
            port.refresh_links()

    def boundingRect(self) -> QRectF:  # type: ignore[override]
        r = self.HIT_RADIUS
        return QRectF(-r, -r, 2 * r, 2 * r)

    def paint(self, painter: QPainter, option, widget=None) -> None:  # type: ignore[override]
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen_color = NODE_BORDER_SELECTED if self.isSelected() else LINK_COLOR
        painter.setPen(QPen(pen_color, 1.5))
        painter.setBrush(QBrush(LINK_COLOR))
        r = self.RADIUS
        painter.drawEllipse(QRectF(-r, -r, 2 * r, 2 * r))

    def itemChange(self, change, value):  # type: ignore[override]
        # Keep the two port items in sync with the dot's position so
        # the link bezier stays glued to the reroute as it's dragged.
        if change == QGraphicsItem.GraphicsItemChange.ItemScenePositionHasChanged:
            self.refresh_all_links()
        return super().itemChange(change, value)
