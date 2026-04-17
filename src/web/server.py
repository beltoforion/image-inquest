"""FastAPI application exposing the flow engine over localhost HTTP.

This is the backend for the browser-based node editor. It reuses
``core/`` and ``nodes/`` unchanged and serves a small static frontend
from ``src/web/static``. It is intended to run **local-only** (bound to
127.0.0.1) and does not implement authentication.
"""
from __future__ import annotations

import base64
import logging
import sys
from enum import Enum
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# Make ``src/`` importable when this module is run via uvicorn with
# ``--app-dir src`` as well as when imported as ``web.server`` from a
# launcher that has already adjusted sys.path.
_SRC_DIR = Path(__file__).resolve().parent.parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from constants import BUILTIN_NODES_DIR, FLOW_DIR, INPUT_DIR, OUTPUT_DIR, USER_NODES_DIR  # noqa: E402
from core.flow import Flow, is_valid_flow_name  # noqa: E402
from core.node_base import NodeBase, NodeParamType  # noqa: E402
from core.node_registry import NodeRegistry  # noqa: E402
from web.flow_io_web import (  # noqa: E402
    FlowIoError,
    load_flow_from,
    save_flow_to,
    serialize_flow,
)

logger = logging.getLogger(__name__)

_STATIC_DIR = Path(__file__).resolve().parent / "static"


# ── Registry (scanned once at startup) ────────────────────────────────────────

_registry = NodeRegistry()


def _build_registry() -> NodeRegistry:
    registry = NodeRegistry()
    errors = registry.scan_builtin(BUILTIN_NODES_DIR)
    errors += registry.scan_user(USER_NODES_DIR)
    for err in errors:
        logger.warning("Node scan error: %s", err)
    return registry


# ── Helpers ───────────────────────────────────────────────────────────────────

def _param_descriptor(node: NodeBase) -> list[dict[str, Any]]:
    """Return a JSON-serialisable descriptor of ``node``'s parameters."""
    out: list[dict[str, Any]] = []
    for p in node.params:
        entry: dict[str, Any] = {
            "name": p.name,
            "type": p.param_type.name,
            "default": _jsonable(p.metadata.get("default")),
        }
        if p.param_type is NodeParamType.ENUM and "enum" in p.metadata:
            enum_cls = p.metadata["enum"]
            entry["choices"] = [
                {"name": m.name, "value": _jsonable(m.value)} for m in enum_cls
            ]
        for key in ("min", "max", "step", "mode"):
            if key in p.metadata:
                entry[key] = _jsonable(p.metadata[key])
        out.append(entry)
    return out


def _port_descriptor(node: NodeBase) -> dict[str, list[dict[str, Any]]]:
    return {
        "inputs": [
            {"name": p.name, "types": sorted(t.value for t in p.accepted_types)}
            for p in node.inputs
        ],
        "outputs": [
            {"name": p.name, "types": sorted(t.value for t in p.emits)}
            for p in node.outputs
        ],
    }


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return _jsonable(value.value)
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    return value


def _instantiate(class_name: str) -> NodeBase:
    entry = _registry.nodes.get(class_name)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Unknown node: {class_name}")
    import importlib
    try:
        module = importlib.import_module(entry.module)
        cls = getattr(module, entry.class_name)
        return cls()
    except Exception as err:
        raise HTTPException(status_code=500, detail=f"Cannot load {class_name}: {err}") from err


def _encode_preview(image: np.ndarray, max_side: int = 512) -> str:
    """Return a base64-encoded PNG preview of ``image``, shrunk to at
    most ``max_side`` pixels on its longest edge to keep responses small.
    """
    h, w = image.shape[:2]
    scale = min(1.0, max_side / max(h, w))
    if scale < 1.0:
        image = cv2.resize(
            image,
            (int(round(w * scale)), int(round(h * scale))),
            interpolation=cv2.INTER_AREA,
        )
    ok, buf = cv2.imencode(".png", image)
    if not ok:
        raise RuntimeError("Failed to encode preview as PNG")
    return base64.b64encode(buf.tobytes()).decode("ascii")


# ── Pydantic models ──────────────────────────────────────────────────────────

class NodeInstance(BaseModel):
    id: int
    module: str
    class_name: str = Field(alias="class")
    position: list[float] = Field(default_factory=lambda: [0.0, 0.0])
    params: dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class Connection(BaseModel):
    src_node: int
    src_output: int
    dst_node: int
    dst_input: int


class FlowPayload(BaseModel):
    version: int = 1
    name: str = "Untitled_flow"
    nodes: list[NodeInstance] = Field(default_factory=list)
    connections: list[Connection] = Field(default_factory=list)


# ── FastAPI app ──────────────────────────────────────────────────────────────

app = FastAPI(title="Sparklehoof Web")


@app.on_event("startup")
def _on_startup() -> None:
    global _registry
    _registry = _build_registry()
    logger.info("Node registry ready (%d nodes)", len(_registry))


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/nodes")
def list_nodes() -> dict[str, Any]:
    """Describe every registered node, grouped by section.

    Each descriptor includes the class name (used to instantiate on the
    server), the display name, palette section, port list, and parameter
    schema. The frontend uses this to populate the palette and to render
    parameter widgets.
    """
    out: dict[str, list[dict[str, Any]]] = {}
    for section, entries in _registry.nodes_by_section().items():
        bucket: list[dict[str, Any]] = []
        for entry in entries:
            try:
                node = _instantiate(entry.class_name)
            except HTTPException as err:
                logger.warning("Skipping node %s in palette: %s", entry.class_name, err.detail)
                continue
            bucket.append({
                "class": entry.class_name,
                "module": entry.module,
                "display_name": entry.display_name,
                "category": entry.category,
                "ports": _port_descriptor(node),
                "params": _param_descriptor(node),
                "is_reactive": getattr(node, "is_reactive", False),
            })
        out[section] = bucket
    return {"sections": out}


_IMAGE_EXTS = {".jpg", ".jpeg", ".png"}
_VIDEO_EXTS = {".mp4"}
_MEDIA_EXTS = _IMAGE_EXTS | _VIDEO_EXTS


@app.get("/api/browse")
def browse(path: str | None = None, filter: str = "media") -> dict[str, Any]:
    """List directory entries so the frontend can implement a file dialog.

    ``path`` is an absolute filesystem path. When omitted, defaults to
    the project's ``input/`` directory so the user starts somewhere
    useful. ``filter`` is one of ``"media"`` (images + video),
    ``"image"``, or ``"all"`` — it hides non-matching *files* but never
    hides directories so the user can always navigate in.

    This is safe because the server is bound to 127.0.0.1; the only
    actor reaching it is the local user, who already has full
    filesystem access. We still resolve the path (no ``..`` tricks
    leaking through symlinks) and fall back to the user's home
    directory on permission errors.
    """
    if path:
        target = Path(path).expanduser()
    else:
        target = INPUT_DIR if INPUT_DIR.is_dir() else Path.home()
    try:
        target = target.resolve(strict=False)
    except OSError:
        target = Path.home()
    if not target.is_dir():
        target = target.parent if target.parent.is_dir() else Path.home()

    allow: set[str] | None
    if filter == "image":
        allow = _IMAGE_EXTS
    elif filter == "media":
        allow = _MEDIA_EXTS
    else:
        allow = None  # show everything

    try:
        raw_entries = list(target.iterdir())
    except PermissionError as err:
        raise HTTPException(status_code=403, detail=str(err)) from err

    entries: list[dict[str, Any]] = []
    for entry in raw_entries:
        try:
            is_dir = entry.is_dir()
        except OSError:
            continue
        if entry.name.startswith("."):
            continue
        if not is_dir and allow is not None and entry.suffix.lower() not in allow:
            continue
        entries.append({"name": entry.name, "is_dir": is_dir})
    entries.sort(key=lambda e: (not e["is_dir"], e["name"].lower()))

    parent = str(target.parent) if target.parent != target else None
    return {
        "path": str(target),
        "parent": parent,
        "entries": entries,
    }


@app.get("/api/flows")
def list_flows() -> dict[str, list[str]]:
    FLOW_DIR.mkdir(parents=True, exist_ok=True)
    names = sorted(p.stem for p in FLOW_DIR.glob("*.flowjs"))
    return {"flows": names}


@app.get("/api/flows/{name}")
def get_flow(name: str) -> dict[str, Any]:
    if not is_valid_flow_name(name):
        raise HTTPException(status_code=400, detail="Invalid flow name")
    path = FLOW_DIR / f"{name}.flowjs"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Flow not found")
    try:
        flow, positioned = load_flow_from(path)
    except FlowIoError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    positions = {id(p.node): p.position for p in positioned}
    return serialize_flow(flow, positions)


@app.put("/api/flows/{name}")
def save_flow(name: str, payload: FlowPayload) -> dict[str, str]:
    if not is_valid_flow_name(name):
        raise HTTPException(status_code=400, detail="Invalid flow name")
    payload.name = name
    flow, positions = _build_flow(payload)
    path = FLOW_DIR / f"{name}.flowjs"
    save_flow_to(path, flow, positions)
    return {"status": "ok", "path": str(path)}


@app.post("/api/run")
def run_flow(payload: FlowPayload) -> dict[str, Any]:
    """Execute a flow posted as JSON. Returns per-node previews.

    Previews are PNGs of each output port's last-emitted image, base64
    encoded. This matches the behaviour of the desktop viewer dock.
    """
    flow, _ = _build_flow(payload)
    try:
        flow.run()
    except Exception as err:
        logger.exception("Flow run failed")
        raise HTTPException(status_code=400, detail=f"Run failed: {err}") from err

    previews: dict[str, Any] = {}
    for idx, node in enumerate(flow.nodes):
        node_previews: list[dict[str, Any]] = []
        for out_idx, port in enumerate(node.outputs):
            last = port.last_emitted
            if last is None or last.is_end_of_stream():
                continue
            try:
                node_previews.append({
                    "output": out_idx,
                    "name": port.name,
                    "png_b64": _encode_preview(last.image),
                })
            except Exception:
                logger.exception("Failed to encode preview for node %d port %d", idx, out_idx)
        if node_previews:
            previews[str(idx)] = node_previews
    return {"status": "ok", "previews": previews}


# ── Flow construction (payload → live Flow) ──────────────────────────────────

def _build_flow(payload: FlowPayload) -> tuple[Flow, dict[int, tuple[float, float]]]:
    flow = Flow(name=payload.name)
    id_to_node: dict[int, NodeBase] = {}
    positions: dict[int, tuple[float, float]] = {}

    for entry in payload.nodes:
        node = _instantiate(entry.class_name)
        for k, v in entry.params.items():
            try:
                setattr(node, k, v)
            except Exception:
                logger.warning("Ignoring param %s on %s (%r)", k, entry.class_name, v)
        flow.add_node(node)
        id_to_node[entry.id] = node
        positions[id(node)] = (float(entry.position[0]), float(entry.position[1]))

    for conn in payload.connections:
        src = id_to_node.get(conn.src_node)
        dst = id_to_node.get(conn.dst_node)
        if src is None or dst is None:
            raise HTTPException(status_code=400, detail=f"Bad connection: {conn}")
        try:
            flow.connect(src, conn.src_output, dst, conn.dst_input)
        except (IndexError, TypeError) as err:
            raise HTTPException(status_code=400, detail=f"Bad connection: {err}") from err

    return flow, positions


# ── Static frontend ───────────────────────────────────────────────────────────

if _STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


@app.get("/")
def index() -> FileResponse:
    index_file = _STATIC_DIR / "index.html"
    if not index_file.is_file():
        raise HTTPException(status_code=404, detail="Frontend not built")
    return FileResponse(str(index_file))


# Expose input/output directories so the browser can preview local
# files; both paths are fixed at module import time and cannot be
# overridden by the client, keeping scope limited to the project tree.
if INPUT_DIR.is_dir():
    app.mount("/files/input", StaticFiles(directory=str(INPUT_DIR)), name="input_files")
if OUTPUT_DIR.is_dir():
    app.mount("/files/output", StaticFiles(directory=str(OUTPUT_DIR)), name="output_files")
