"""Unit tests for the HSL (HLS) split / join filters."""
from __future__ import annotations

import cv2
import numpy as np

from core.io_data import IoData, IoDataType
from core.port import InputPort
from nodes.filters.hsl_join import HslJoin
from nodes.filters.hsl_split import HslSplit


def _grey(value: int) -> IoData:
    return IoData.from_greyscale(np.full((2, 2), value, dtype=np.uint8))


# ── HslSplit ───────────────────────────────────────────────────────────────────

def test_hsl_split_emits_three_grey_planes_in_hsl_order() -> None:
    """Output order is H, S, L — matching the user-facing HSL convention,
    even though OpenCV stores the planes as H, L, S internally."""
    node = HslSplit()
    image = np.full((3, 4, 3), (10, 20, 200), dtype=np.uint8)  # BGR
    node.inputs[0].receive(IoData.from_image(image))

    h_port, s_port, l_port = node.outputs
    expected = cv2.cvtColor(image, cv2.COLOR_BGR2HLS_FULL)
    np.testing.assert_array_equal(h_port.last_emitted.image, expected[..., 0])
    np.testing.assert_array_equal(l_port.last_emitted.image, expected[..., 1])
    np.testing.assert_array_equal(s_port.last_emitted.image, expected[..., 2])


def test_hsl_split_drops_alpha_from_bgra() -> None:
    node = HslSplit()
    bgra = np.full((2, 2, 4), (10, 20, 200, 64), dtype=np.uint8)
    node.inputs[0].receive(IoData.from_image(bgra))

    bgr = cv2.cvtColor(bgra, cv2.COLOR_BGRA2BGR)
    expected = cv2.cvtColor(bgr, cv2.COLOR_BGR2HLS_FULL)
    h, s, l = (p.last_emitted.image for p in node.outputs)
    np.testing.assert_array_equal(h, expected[..., 0])
    np.testing.assert_array_equal(s, expected[..., 2])
    np.testing.assert_array_equal(l, expected[..., 1])


# ── HslJoin ────────────────────────────────────────────────────────────────────

def test_hsl_join_merges_three_planes_into_bgr() -> None:
    node = HslJoin()
    node.inputs[0].receive(_grey(50))   # H
    node.inputs[1].receive(_grey(200))  # S
    node.inputs[2].receive(_grey(150))  # L

    out = node.outputs[0].last_emitted
    assert out is not None and out.type == IoDataType.IMAGE
    assert out.image.shape == (2, 2, 3)


# ── Round-trip ─────────────────────────────────────────────────────────────────

def test_hsl_split_join_roundtrip_preserves_grey() -> None:
    """Greys (R == G == B) round-trip exactly — saturation is zero so
    the hue is irrelevant and there is no chroma quantisation."""
    split = HslSplit()
    join = HslJoin()
    for i in range(3):
        split.outputs[i].connect(join.inputs[i])
    capture = InputPort("cap", {IoDataType.IMAGE})
    join.outputs[0].connect(capture)

    rng = np.random.default_rng(0)
    grey_plane = rng.integers(0, 256, size=(8, 8), dtype=np.uint8)
    original = np.dstack([grey_plane, grey_plane, grey_plane])
    split.inputs[0].receive(IoData.from_image(original))

    assert capture.has_data
    np.testing.assert_array_equal(capture.data.image, original)


def test_hsl_split_join_roundtrip_is_close_for_arbitrary_bgr() -> None:
    """Arbitrary BGR pixels round-trip approximately: HLS ↔ BGR at
    uint8 precision is not bit-exact (the hue buckets do not align
    1:1 with the RGB buckets), but the per-pixel error stays small.

    Bound is empirical — chosen large enough to absorb worst-case
    quantisation noise on a uniformly-random colour field, small
    enough that a genuinely broken conversion (wrong cvtColor flag,
    swapped channels) trips it."""
    split = HslSplit()
    join = HslJoin()
    for i in range(3):
        split.outputs[i].connect(join.inputs[i])
    capture = InputPort("cap", {IoDataType.IMAGE})
    join.outputs[0].connect(capture)

    rng = np.random.default_rng(0)
    original = rng.integers(0, 256, size=(8, 8, 3), dtype=np.uint8)
    split.inputs[0].receive(IoData.from_image(original))

    assert capture.has_data
    diff = np.abs(capture.data.image.astype(int) - original.astype(int))
    assert diff.max() <= 8
