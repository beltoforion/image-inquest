from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QPushButton, QWidget, QMenuBar, QMenu,
    QGraphicsView, QGraphicsScene, QGraphicsItem,
    QGraphicsEllipseItem, QGraphicsPathItem,
)
from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import (
    QPainter, QPen, QBrush, QColor, QPainterPath, QPainterPathStroker, QFont,
)

from core.flow import Flow
from ui.page import Page

if TYPE_CHECKING:
    from ui.page_manager import PageManager


# ── Node editor visual constants ──────────────────────────────────────────────

_PORT_RADIUS = 7
_NODE_WIDTH = 180
_NODE_HEADER_H = 30
_PORT_START_Y = 18   # distance from header bottom to first port centre
_PORT_SPACING = 26   # vertical distance between successive ports


# ── Graphics items ─────────────────────────────────────────────────────────────

class NodePort(QGraphicsEllipseItem):
    """A small circle representing an input or output connection point."""

    INPUT = "input"
    OUTPUT = "output"

    def __init__(self, node: NodeItem, port_type: str) -> None:
        r = _PORT_RADIUS
        super().__init__(-r, -r, r * 2, r * 2, node)
        self._node = node
        self._port_type = port_type
        self._connections: list[EdgeItem] = []

        color = QColor("#6699dd") if port_type == self.INPUT else QColor("#dd9944")
        self.setBrush(QBrush(color))
        self.setPen(QPen(QColor("#cccccc"), 1.5))
        self.setZValue(2)

    @property
    def port_type(self) -> str:
        return self._port_type

    @property
    def node(self) -> NodeItem:
        return self._node

    def scene_center(self) -> QPointF:
        return self.mapToScene(QPointF(0.0, 0.0))

    def add_connection(self, edge: EdgeItem) -> None:
        self._connections.append(edge)

    def remove_connection(self, edge: EdgeItem) -> None:
        if edge in self._connections:
            self._connections.remove(edge)

    def remove_all_connections(self) -> None:
        for edge in list(self._connections):
            edge.detach()


class EdgeItem(QGraphicsPathItem):
    """A cubic bezier curve connecting an output port to an input port."""

    def __init__(self, src: NodePort, dst: NodePort) -> None:
        super().__init__()
        self._src = src
        self._dst = dst
        self.setPen(QPen(QColor("#aaaaaa"), 2.0))
        self.setZValue(-1)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.update_path()

    def update_path(self) -> None:
        p1 = self._src.scene_center()
        p2 = self._dst.scene_center()
        dx = abs(p2.x() - p1.x()) * 0.5
        path = QPainterPath(p1)
        path.cubicTo(p1.x() + dx, p1.y(), p2.x() - dx, p2.y(), p2.x(), p2.y())
        self.setPath(path)

    def shape(self) -> QPainterPath:
        # Widen the clickable area so right-click is easier to land.
        stroker = QPainterPathStroker()
        stroker.setWidth(12)
        return stroker.createStroke(self.path())

    def detach(self) -> None:
        """Disconnect this edge from both ports and remove it from the scene."""
        self._src.remove_connection(self)
        self._dst.remove_connection(self)
        if self.scene():
            self.scene().removeItem(self)


class NodeItem(QGraphicsItem):
    """A draggable node rectangle with labelled input and output ports."""

    def __init__(self, label: str, num_inputs: int = 1, num_outputs: int = 1) -> None:
        super().__init__()
        self._label = label
        self._input_ports: list[NodePort] = []
        self._output_ports: list[NodePort] = []

        num_port_rows = max(num_inputs, num_outputs, 1)
        self._height = _NODE_HEADER_H + _PORT_START_Y + num_port_rows * _PORT_SPACING + 10

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setZValue(1)

        for i in range(num_inputs):
            port = NodePort(self, NodePort.INPUT)
            port.setPos(0.0, _NODE_HEADER_H + _PORT_START_Y + i * _PORT_SPACING)
            self._input_ports.append(port)

        for i in range(num_outputs):
            port = NodePort(self, NodePort.OUTPUT)
            port.setPos(_NODE_WIDTH, _NODE_HEADER_H + _PORT_START_Y + i * _PORT_SPACING)
            self._output_ports.append(port)

    def all_ports(self) -> list[NodePort]:
        return self._input_ports + self._output_ports

    # ── QGraphicsItem interface ────────────────────────────────────────────────

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, _NODE_WIDTH, self._height)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        selected = self.isSelected()

        # Body
        body_pen = QPen(QColor("#888888") if selected else QColor("#555555"), 1.5)
        painter.setPen(body_pen)
        painter.setBrush(QBrush(QColor("#2b2b2b")))
        painter.drawRoundedRect(QRectF(0, 0, _NODE_WIDTH, self._height), 5, 5)

        # Header (clipped to rounded top)
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(0, 0, _NODE_WIDTH, self._height), 5, 5)
        painter.setClipPath(clip)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor("#3d5a8a")))
        painter.drawRect(QRectF(0, 0, _NODE_WIDTH, _NODE_HEADER_H))
        painter.setClipping(False)

        # Header label
        font = QFont()
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QPen(Qt.GlobalColor.white))
        painter.drawText(
            QRectF(8, 0, _NODE_WIDTH - 16, _NODE_HEADER_H),
            Qt.AlignmentFlag.AlignVCenter,
            self._label,
        )

        # Port labels
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(QPen(QColor("#bbbbbb")))
        for port in self._input_ports:
            painter.drawText(
                QRectF(10, port.y() - 8, _NODE_WIDTH / 2 - 14, 16),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                "Input",
            )
        for port in self._output_ports:
            painter.drawText(
                QRectF(_NODE_WIDTH / 2, port.y() - 8, _NODE_WIDTH / 2 - 10, 16),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                "Output",
            )

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            for port in self.all_ports():
                for edge in port._connections:
                    edge.update_path()
        return super().itemChange(change, value)

    def remove(self) -> None:
        for port in self.all_ports():
            port.remove_all_connections()
        if self.scene():
            self.scene().removeItem(self)


# ── Scene & View ───────────────────────────────────────────────────────────────

class NodeEditorScene(QGraphicsScene):
    def __init__(self) -> None:
        super().__init__()
        self.setBackgroundBrush(QBrush(QColor("#1e1e1e")))

    def add_node(self, label: str, num_inputs: int = 1, num_outputs: int = 1) -> NodeItem:
        existing = sum(1 for item in self.items() if isinstance(item, NodeItem))
        node = NodeItem(label, num_inputs, num_outputs)
        self.addItem(node)
        node.setPos(40 + existing * 20, 40 + existing * 20)
        return node

    def clear_nodes(self) -> None:
        for item in list(self.items()):
            if isinstance(item, NodeItem):
                item.remove()


class NodeEditorView(QGraphicsView):
    """QGraphicsView that handles port-to-port edge dragging."""

    def __init__(self, scene: NodeEditorScene) -> None:
        super().__init__(scene)
        self._node_scene = scene
        self._drag_src: NodePort | None = None
        self._temp_edge: QGraphicsPathItem | None = None

        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.MinimalViewportUpdate)

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _port_at(self, scene_pos: QPointF) -> NodePort | None:
        for item in self.scene().items(scene_pos):
            if isinstance(item, NodePort):
                return item
        return None

    def _update_temp_edge(self, dst: QPointF) -> None:
        assert self._drag_src is not None and self._temp_edge is not None
        p1 = self._drag_src.scene_center()
        dx = abs(dst.x() - p1.x()) * 0.5
        path = QPainterPath(p1)
        path.cubicTo(p1.x() + dx, p1.y(), dst.x() - dx, dst.y(), dst.x(), dst.y())
        self._temp_edge.setPath(path)

    # ── Mouse events ───────────────────────────────────────────────────────────

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            scene_pos = self.mapToScene(event.position().toPoint())
            port = self._port_at(scene_pos)
            if port is not None and port.port_type == NodePort.OUTPUT:
                self._drag_src = port
                self._temp_edge = QGraphicsPathItem()
                self._temp_edge.setPen(QPen(QColor("#ffffff"), 1.5, Qt.PenStyle.DashLine))
                self._temp_edge.setZValue(100)
                self._node_scene.addItem(self._temp_edge)
                self._update_temp_edge(scene_pos)
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_src is not None:
            self._update_temp_edge(self.mapToScene(event.position().toPoint()))
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._drag_src is not None:
            if self._temp_edge is not None:
                self._node_scene.removeItem(self._temp_edge)
                self._temp_edge = None

            scene_pos = self.mapToScene(event.position().toPoint())
            dst = self._port_at(scene_pos)
            if (
                dst is not None
                and dst.port_type == NodePort.INPUT
                and dst.node is not self._drag_src.node
            ):
                edge = EdgeItem(self._drag_src, dst)
                self._node_scene.addItem(edge)
                self._drag_src.add_connection(edge)
                dst.add_connection(edge)

            self._drag_src = None
            return
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event) -> None:
        scene_pos = self.mapToScene(event.pos())
        for item in self.scene().items(scene_pos):
            if isinstance(item, EdgeItem):
                menu = QMenu(self)
                menu.addAction("Delete Connection", item.detach)
                menu.exec(self.mapToGlobal(event.pos()))
                return
        super().contextMenuEvent(event)

    def wheelEvent(self, event) -> None:
        factor = 1.15 if event.angleDelta().y() > 0 else 1.0 / 1.15
        self.scale(factor, factor)


# ── Page ───────────────────────────────────────────────────────────────────────

class NodeEditorPage(Page):
    name = "editor"

    def __init__(self, menu_bar: QMenuBar, page_manager: PageManager) -> None:
        self._node_count: int = 0
        self._flow: Flow | None = None
        self._node_scene: NodeEditorScene | None = None
        self._node_view: NodeEditorView | None = None
        super().__init__(menu_bar=menu_bar, page_manager=page_manager)

    def set_flow(self, flow: Flow) -> None:
        self._flow = flow

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        toolbar = QWidget()
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(8, 6, 8, 6)
        add_btn = QPushButton("Add Node")
        add_btn.clicked.connect(self._on_add_node)
        clear_btn = QPushButton("Clear All")
        clear_btn.clicked.connect(self._on_clear_nodes)
        toolbar_layout.addWidget(add_btn)
        toolbar_layout.addWidget(clear_btn)
        toolbar_layout.addStretch()
        layout.addWidget(toolbar)

        self._node_scene = NodeEditorScene()
        self._node_view = NodeEditorView(self._node_scene)
        layout.addWidget(self._node_view)

    def _install_menus(self) -> None:
        menu = self._menu_bar.addMenu("Node Editor")
        menu.addAction("Add Node", self._on_add_node)
        menu.addAction("Clear All", self._on_clear_nodes)
        menu.addSeparator()
        menu.addAction("Exit", self._on_exit_clicked)
        self._menus.append(menu)

    def _on_add_node(self) -> None:
        self._node_count += 1
        self._node_scene.add_node(f"Node {self._node_count}")

    def _on_clear_nodes(self) -> None:
        self._node_scene.clear_nodes()
        self._node_count = 0

    def _on_exit_clicked(self) -> None:
        self._on_clear_nodes()
        self._page_manager.activate(self._page_manager.start_page)
