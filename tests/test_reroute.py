"""Tests for the Reroute pass-through node.

Covers the core contract (pass-through semantics, port typing) in
pure Python, plus the editor-side behaviour (double-click inserts,
delete-reconnect) under a headless Qt application.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest

from core.io_data import IMAGE_TYPES, IoData, IoDataType
from core.port import InputPort
from nodes.util.reroute import Reroute


# ── Core contract ──────────────────────────────────────────────────────────────


def test_reroute_has_one_input_and_one_output_both_image_types() -> None:
    node = Reroute()
    assert len(node.inputs) == 1
    assert len(node.outputs) == 1
    assert node.inputs[0].accepted_types == frozenset(IMAGE_TYPES)
    assert node.outputs[0].emits == frozenset(IMAGE_TYPES)


def test_reroute_forwards_input_payload_verbatim() -> None:
    """process_impl(inputs[0].data) → outputs[0]; the IoData object
    is sent through as-is, no copy, no type change."""
    node = Reroute()
    capture = InputPort("cap", set(IMAGE_TYPES))
    node.outputs[0].connect(capture)

    payload = IoData.from_image(np.full((4, 4, 3), 42, dtype=np.uint8))
    node.inputs[0].receive(payload)  # triggers dispatch

    assert capture.has_data
    assert capture.data is payload  # identity, not just equality


def test_reroute_preserves_greyscale_type() -> None:
    """A grey frame entering a reroute must emerge as IMAGE_GREY, not
    silently demoted to IMAGE. The pass-through uses the original
    IoData object, so the type discriminator is preserved."""
    node = Reroute()
    capture = InputPort("cap", set(IMAGE_TYPES))
    node.outputs[0].connect(capture)

    grey = IoData.from_greyscale(np.full((4, 4), 77, dtype=np.uint8))
    node.inputs[0].receive(grey)

    assert capture.data.type == IoDataType.IMAGE_GREY


def test_reroute_is_marked_hidden_from_palette() -> None:
    """The Reroute uses the "__hidden__" section sentinel so the
    palette scanner can filter it out — only the editor's
    double-click-to-insert flow should ever create one."""
    assert Reroute().section == "__hidden__"


# ── Editor behaviour (needs Qt) ────────────────────────────────────────────────

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication

from core.flow import Flow
from nodes.filters.grayscale import Grayscale
from nodes.sources.image_source import ImageSource
from ui.flow_scene import FlowScene
from ui.reroute_node_item import RerouteNodeItem


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication(sys.argv)


def _wired_scene() -> tuple[FlowScene, "LinkItem"]:
    """Return a fresh scene with Source → Grayscale and the joining link."""
    scene = FlowScene()
    scene.set_flow(Flow(name="reroute_test"))
    src = scene.add_node(ImageSource(), QPointF(0, 0))
    dst = scene.add_node(Grayscale(), QPointF(400, 0))
    link = scene.connect_ports(src.output_ports[0], dst.input_ports[0])
    assert link is not None
    return scene, link


def test_insert_reroute_on_link_replaces_it_with_two_links(
    qapp: QApplication,
) -> None:
    scene, link = _wired_scene()
    scene._insert_reroute_on_link(link, QPointF(200, 0))

    # Original link is gone; two new links plus one reroute node exist.
    items = scene.iter_node_items()
    reroutes = [it for it in items if isinstance(it, RerouteNodeItem)]
    assert len(reroutes) == 1
    assert len(scene.iter_links()) == 2


def test_insert_reroute_preserves_source_to_sink_path(
    qapp: QApplication,
) -> None:
    """After insertion, the source's output still reaches the sink's
    input via the reroute — the graph semantics haven't changed."""
    scene, link = _wired_scene()
    src_port = link.src_port
    dst_port = link.dst_port
    scene._insert_reroute_on_link(link, QPointF(200, 0))

    [reroute_item] = [
        it for it in scene.iter_node_items() if isinstance(it, RerouteNodeItem)
    ]
    # src → reroute.in, reroute.out → dst
    assert reroute_item.input_ports[0].model.upstream is src_port.model
    assert dst_port.model.upstream is reroute_item.output_ports[0].model


def test_deleting_reroute_reconnects_upstream_to_downstream(
    qapp: QApplication,
) -> None:
    """A reroute is a pure visual aid — removing it must re-join its
    two halves so the pipeline keeps working."""
    scene, link = _wired_scene()
    src_port = link.src_port
    dst_port = link.dst_port
    scene._insert_reroute_on_link(link, QPointF(200, 0))

    [reroute_item] = [
        it for it in scene.iter_node_items() if isinstance(it, RerouteNodeItem)
    ]
    scene.remove_node_item(reroute_item)

    # No reroutes left; a single direct link reconnects src to dst.
    assert all(
        not isinstance(it, RerouteNodeItem) for it in scene.iter_node_items()
    )
    assert dst_port.model.upstream is src_port.model
    assert len(scene.iter_links()) == 1


def test_reroute_is_serialisable_as_a_regular_node(qapp: QApplication) -> None:
    """Reroutes use the normal NodeBase serialisation path, so they
    round-trip through flow_io without special-case code."""
    from ui.flow_io import serialize_flow

    scene, link = _wired_scene()
    scene._insert_reroute_on_link(link, QPointF(200, 0))
    data = serialize_flow(scene, scene.flow)

    classes = {(n["module"], n["class"]) for n in data["nodes"]}
    assert ("nodes.util.reroute", "Reroute") in classes
