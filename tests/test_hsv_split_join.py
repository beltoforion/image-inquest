"""Unit tests for the HSV split / join filters."""
from __future__ import annotations

import cv2
import numpy as np

from core.io_data import IoData, IoDataType
from core.port import InputPort
from nodes.filters.hsv_join import HsvJoin
from nodes.filters.hsv_split import HsvSplit


def _grey(value: int) -> IoData:
    return IoData.from_greyscale(np.full((2, 2), value, dtype=np.uint8))


# ── HsvSplit ───────────────────────────────────────────────────────────────────

def test_hsv_split_emits_three_grey_planes() -> None:
    node = HsvSplit()
    image = np.full((3, 4, 3), (10, 20, 200), dtype=np.uint8)  # BGR
    node.inputs[0].receive(IoData.from_image(image))

    h, s, v = (p.last_emitted for p in node.outputs)
    assert h is not None and h.type == IoDataType.IMAGE_GREY
    assert s is not None and s.type == IoDataType.IMAGE_GREY
    assert v is not None and v.type == IoDataType.IMAGE_GREY
    assert h.image.shape == (3, 4)
    assert s.image.shape == (3, 4)
    assert v.image.shape == (3, 4)


def test_hsv_split_drops_alpha_from_bgra() -> None:
    """A 4-channel BGRA input must split cleanly (alpha is dropped)."""
    node = HsvSplit()
    bgra = np.full((2, 2, 4), (10, 20, 200, 64), dtype=np.uint8)
    node.inputs[0].receive(IoData.from_image(bgra))

    bgr = cv2.cvtColor(bgra, cv2.COLOR_BGRA2BGR)
    expected = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV_FULL)
    h, s, v = (p.last_emitted.image for p in node.outputs)
    np.testing.assert_array_equal(h, expected[..., 0])
    np.testing.assert_array_equal(s, expected[..., 1])
    np.testing.assert_array_equal(v, expected[..., 2])


def test_hsv_split_rejects_greyscale_input() -> None:
    node = HsvSplit()
    grey = np.full((4, 4), 128, dtype=np.uint8)
    try:
        node.inputs[0].receive(IoData.from_image(grey))
    except Exception as exc:
        assert "expects a 3- or 4-channel" in str(exc)
    else:
        raise AssertionError("HsvSplit must reject 1-channel input")


# ── HsvJoin ────────────────────────────────────────────────────────────────────

def test_hsv_join_merges_three_planes_into_bgr() -> None:
    node = HsvJoin()
    node.inputs[0].receive(_grey(50))   # H
    node.inputs[1].receive(_grey(200))  # S
    node.inputs[2].receive(_grey(150))  # V

    out = node.outputs[0].last_emitted
    assert out is not None and out.type == IoDataType.IMAGE
    assert out.image.shape == (2, 2, 3)


# ── Round-trip ─────────────────────────────────────────────────────────────────

def test_hsv_split_join_roundtrip_preserves_grey() -> None:
    """Greys (R == G == B) round-trip exactly — saturation is zero so
    the hue is irrelevant and there is no chroma quantisation."""
    split = HsvSplit()
    join = HsvJoin()
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


def test_hsv_split_join_roundtrip_is_close_for_arbitrary_bgr() -> None:
    """Arbitrary BGR pixels round-trip approximately: HSV ↔ BGR at
    uint8 precision is not bit-exact (the hue buckets do not align
    1:1 with the RGB buckets), but the per-pixel error stays small.

    Bound is empirical — chosen large enough to absorb worst-case
    quantisation noise on a uniformly-random colour field, small
    enough that a genuinely broken conversion (wrong cvtColor flag,
    swapped channels) trips it."""
    split = HsvSplit()
    join = HsvJoin()
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
