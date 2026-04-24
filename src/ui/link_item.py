from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsPathItem

from ui.theme import LINK_COLOR, LINK_SELECTED_COLOR

if TYPE_CHECKING:
    from ui.port_item import PortItem


class LinkItem(QGraphicsPathItem):
    """Bezier connection between two :class:`PortItem` instances.

    The path is recomputed whenever either endpoint moves. Links sit just
    below nodes in the Z order so dragging over them doesn't obscure the
    ports.
    """

    Z_VALUE = -1

    def __init__(self, src_port: PortItem, dst_port: PortItem) -> None:
        super().__init__()
        self._src_port = src_port
        self._dst_port = dst_port
        self.setZValue(self.Z_VALUE)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setPen(QPen(LINK_COLOR, 2))
        self.setAcceptHoverEvents(False)
        src_port.add_link(self)
        dst_port.add_link(self)
        self.update_path()

    # ── Endpoints ──────────────────────────────────────────────────────────────

    @property
    def src_port(self) -> PortItem:
        return self._src_port

    @property
    def dst_port(self) -> PortItem:
        return self._dst_port

    # ── Path ───────────────────────────────────────────────────────────────────

    def update_path(self) -> None:
        """Recompute the bezier from src_port to dst_port.

        Reroute endpoints use a "free" tangent that points towards the
        other endpoint, so a link passing through a reroute renders as
        one smooth S-curve instead of two horizontally-tangent arcs
        that would loop back on themselves whenever the reroute sits
        above / behind its neighbour.
        """
        src = self._src_port.scenePos()
        dst = self._dst_port.scenePos()
        self.setPath(
            _bezier_path(
                src, dst,
                src_tangent=_tangent_for(self._src_port),
                dst_tangent=_tangent_for(self._dst_port),
            )
        )

    def paint(self, painter, option, widget=None) -> None:  # type: ignore[override]
        pen = QPen(LINK_SELECTED_COLOR if self.isSelected() else LINK_COLOR, 2)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(pen)
        painter.drawPath(self.path())

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def detach(self) -> None:
        """Unregister this link from both ports. Call before removing from
        the scene to prevent dangling references."""
        self._src_port.remove_link(self)
        self._dst_port.remove_link(self)


def _tangent_for(port_item) -> QPointF | None:
    """Return the unit tangent vector the bezier should follow at ``port_item``.

    Ports on a standard node are fixed: outputs point rightward,
    inputs accept from the right. A port on a reroute has no preferred
    direction — return ``None`` so the bezier picks a tangent aimed at
    the other endpoint, which gives smooth S-curves for mäandrierende
    Flows (Blender / UE style).
    """
    if getattr(port_item.node_item, "is_reroute", False):
        return None
    return QPointF(1.0, 0.0) if port_item.kind == "output" else QPointF(-1.0, 0.0)


def _bezier_path(
    src: QPointF,
    dst: QPointF,
    *,
    src_tangent: QPointF | None,
    dst_tangent: QPointF | None,
) -> QPainterPath:
    """Cubic bezier between two points with configurable endpoint tangents.

    ``*_tangent`` is a unit vector pointing *out of* the endpoint along
    the bezier's first derivative. Passing ``None`` means "free" — the
    tangent is aimed at the other endpoint, so a reroute-anchored link
    curves naturally towards its neighbour instead of being forced to
    leave horizontally.
    """
    path = QPainterPath(src)
    dx = max(60.0, abs(dst.x() - src.x()) * 0.5)

    def _offset(tangent: QPointF | None, anchor: QPointF, other: QPointF) -> QPointF:
        if tangent is not None:
            return QPointF(tangent.x() * dx, tangent.y() * dx)
        # Free tangent: point from anchor toward the other endpoint,
        # scaled so the curve has comparable bend to the fixed case.
        return QPointF((other.x() - anchor.x()) * 0.4, (other.y() - anchor.y()) * 0.4)

    ctrl1 = src + _offset(src_tangent, src, dst)
    ctrl2 = dst + _offset(dst_tangent, dst, src)
    path.cubicTo(ctrl1, ctrl2, dst)
    return path


class PendingLinkItem(QGraphicsPathItem):
    """Temporary link shown while the user is dragging a new connection."""

    Z_VALUE = -1

    def __init__(self, start: QPointF) -> None:
        super().__init__()
        self.setZValue(self.Z_VALUE)
        self.setPen(QPen(LINK_COLOR, 1, Qt.PenStyle.DashLine))
        self._start = start
        self._end = start
        self._rebuild()

    def update_end(self, end: QPointF) -> None:
        self._end = end
        self._rebuild()

    def _rebuild(self) -> None:
        # The pending (drag-in-progress) link doesn't have a second
        # endpoint yet, so just use the classic horizontal tangents.
        # The tangent shape only matters once the drop target is known.
        self.setPath(
            _bezier_path(
                self._start, self._end,
                src_tangent=QPointF(1.0, 0.0),
                dst_tangent=QPointF(-1.0, 0.0),
            )
        )
