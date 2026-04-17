"""JSON serialization for flows without any Qt dependency.

Mirrors the ``.flowjs`` format produced by :mod:`ui.flow_io` so that files
saved from the desktop editor open in the web editor and vice versa. The
difference is that this module stores node positions on the nodes
themselves (we have no QGraphicsItem to ask) and resolves node classes
via the :class:`NodeRegistry` entries instead of importing arbitrary
modules.
"""
from __future__ import annotations

import importlib
import json
import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from core.flow import Flow
from core.node_base import NodeBase

logger = logging.getLogger(__name__)

FLOW_FORMAT_VERSION: int = 1


class FlowIoError(Exception):
    """Raised when a flow file cannot be read, parsed, or version-matched."""


@dataclass
class PositionedNode:
    node: NodeBase
    position: tuple[float, float]


def serialize_flow(
    flow: Flow,
    positions: dict[int, tuple[float, float]],
) -> dict:
    """Return a JSON-compatible snapshot of ``flow``.

    ``positions`` maps ``id(node)`` to ``(x, y)`` so the web editor can
    restore each node's canvas location. Missing entries default to
    ``(0, 0)``.
    """
    nodes = flow.nodes
    node_ids = {id(n): idx for idx, n in enumerate(nodes)}

    nodes_out: list[dict] = []
    for idx, node in enumerate(nodes):
        pos = positions.get(id(node), (0.0, 0.0))
        params = {p.name: _jsonable(getattr(node, p.name, None)) for p in node.params}
        nodes_out.append({
            "id":       idx,
            "module":   type(node).__module__,
            "class":    type(node).__name__,
            "position": [float(pos[0]), float(pos[1])],
            "params":   params,
        })

    connections_out: list[dict] = []
    for src_idx, src_node in enumerate(nodes):
        for out_idx, out_port in enumerate(src_node.outputs):
            for dst_port in out_port.connections:
                for dst_idx, dst_node in enumerate(nodes):
                    if dst_port in dst_node.inputs:
                        in_idx = dst_node.inputs.index(dst_port)
                        connections_out.append({
                            "src_node":   src_idx,
                            "src_output": out_idx,
                            "dst_node":   dst_idx,
                            "dst_input":  in_idx,
                        })
                        break

    return {
        "version":     FLOW_FORMAT_VERSION,
        "name":        flow.name,
        "nodes":       nodes_out,
        "connections": connections_out,
    }


def save_flow_to(path: Path, flow: Flow, positions: dict[int, tuple[float, float]]) -> None:
    data = serialize_flow(flow, positions)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_flow_from(path: Path) -> tuple[Flow, list[PositionedNode]]:
    """Load a flow from a .flowjs file.

    Returns the ``Flow`` and a list of ``PositionedNode`` in registration
    order, so callers (e.g. the web API) can echo positions back to the
    client.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as err:
        raise FlowIoError(f"Cannot read file: {err}") from err
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as err:
        raise FlowIoError(f"Invalid JSON: {err}") from err

    version = data.get("version")
    if version != FLOW_FORMAT_VERSION:
        raise FlowIoError(f"Unsupported format version: {version!r}")

    flow = Flow(name=data.get("name", path.stem))
    id_to_node: dict[int, NodeBase] = {}
    positioned: list[PositionedNode] = []

    for entry in data.get("nodes", []):
        node = _instantiate_node(entry)
        if node is None:
            continue
        flow.add_node(node)
        id_to_node[entry["id"]] = node
        pos = entry.get("position") or [0.0, 0.0]
        positioned.append(PositionedNode(node=node, position=(float(pos[0]), float(pos[1]))))

    for conn in data.get("connections", []):
        src = id_to_node.get(conn.get("src_node"))
        dst = id_to_node.get(conn.get("dst_node"))
        if src is None or dst is None:
            continue
        try:
            src.outputs[conn["src_output"]].connect(dst.inputs[conn["dst_input"]])
        except (IndexError, KeyError, TypeError):
            logger.warning("Skipping invalid connection: %s", conn)

    return flow, positioned


def _instantiate_node(entry: dict) -> NodeBase | None:
    module_name = entry.get("module", "")
    class_name = entry.get("class", "")
    try:
        module = importlib.import_module(module_name)
        cls = getattr(module, class_name)
    except (ImportError, AttributeError):
        logger.exception("Cannot resolve node %s.%s", module_name, class_name)
        return None

    try:
        node: NodeBase = cls()
    except Exception:
        logger.exception("Failed to instantiate %s.%s", module_name, class_name)
        return None

    for name, value in (entry.get("params") or {}).items():
        try:
            setattr(node, name, value)
        except Exception:
            logger.warning(
                "Ignoring param %s on %s.%s (%r)", name, module_name, class_name, value,
            )
    return node


def _jsonable(value: object) -> object:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return _jsonable(value.value)
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    return value
