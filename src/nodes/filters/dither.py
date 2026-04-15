from __future__ import annotations

import math
from enum import IntEnum

import cv2
import numpy as np
from typing_extensions import override

from core.io_data import IoData, IoDataType
from core.node_base import NodeBase, NodeParam, NodeParamType
from core.port import InputPort, OutputPort


class DitherMethod(IntEnum):
    """Dithering algorithms supported by :class:`Dither`.

    The integer values match the ``method`` parameter so the node can
    be driven from a plain INT UI control until a dedicated enum param
    type exists.
    """
    BAYER2          = 1
    BAYER4          = 2
    BAYER8          = 3
    NOISE           = 4
    FLOYD_STEINBERG = 5
    STUCKI          = 6
    ATKINSON        = 7
    BURKES          = 8
    SIERRA          = 9
    DIFFUSION_X     = 10
    DIFFUSION_XY    = 11


# Error-diffusion kernels laid out as (dy, dx, weight) triples — one
# entry per neighbour that should receive a share of the quantisation
# error. Matches the original OCVL layout (rows: current/next/next+1;
# columns: x-2 .. x+2) but flattened so the inner loop is a simple
# iteration instead of 12 guarded index expressions.
_DIFFUSION_KERNELS: dict[DitherMethod, tuple[tuple[int, int, float], ...]] = {
    DitherMethod.FLOYD_STEINBERG: (
        (0, +1, 7 / 16),
        (1, -1, 3 / 16), (1,  0, 5 / 16), (1, +1, 1 / 16),
    ),
    DitherMethod.STUCKI: (
        (0, +1, 8 / 42), (0, +2, 4 / 42),
        (1, -2, 2 / 42), (1, -1, 4 / 42), (1, 0, 8 / 42),
        (1, +1, 4 / 42), (1, +2, 2 / 42),
        (2, -2, 1 / 42), (2, -1, 2 / 42), (2, 0, 4 / 42),
        (2, +1, 2 / 42), (2, +2, 1 / 42),
    ),
    DitherMethod.ATKINSON: (
        (0, +1, 1 / 8), (0, +2, 1 / 8),
        (1, -1, 1 / 8), (1, 0, 1 / 8), (1, +1, 1 / 8),
        (2,  0, 1 / 8),
    ),
    DitherMethod.BURKES: (
        (0, +1, 8 / 32), (0, +2, 4 / 32),
        (1, -2, 2 / 32), (1, -1, 4 / 32), (1, 0, 8 / 32),
        (1, +1, 4 / 32), (1, +2, 2 / 32),
    ),
    DitherMethod.SIERRA: (
        (0, +1, 5 / 32), (0, +2, 3 / 32),
        (1, -2, 2 / 32), (1, -1, 4 / 32), (1, 0, 5 / 32),
        (1, +1, 4 / 32), (1, +2, 2 / 32),
        (2, -1, 2 / 32), (2,  0, 3 / 32), (2, +1, 2 / 32),
    ),
    DitherMethod.DIFFUSION_X: (
        (0, +1, 1.0),
    ),
    DitherMethod.DIFFUSION_XY: (
        (0, +1, 0.5), (1, 0, 0.5),
    ),
}

# Bayer ordered-dither matrices (2×2, 4×4, 8×8) — pre-computed so the
# tiling step in ``process`` is a pure ``np.tile``.
_BAYER_MATRICES: dict[DitherMethod, np.ndarray] = {
    DitherMethod.BAYER2: np.array([
        [0, 2],
        [3, 1],
    ]),
    DitherMethod.BAYER4: np.array([
        [ 0,  8,  2, 10],
        [12,  4, 14,  6],
        [ 3, 11,  1,  9],
        [15,  7, 13,  5],
    ]),
    DitherMethod.BAYER8: np.array([
        [ 0, 32,  8, 40,  2, 34, 10, 42],
        [48, 16, 56, 24, 50, 18, 58, 26],
        [12, 44,  4, 36, 14, 46,  6, 38],
        [60, 28, 52, 20, 62, 30, 54, 22],
        [ 3, 35, 11, 43,  1, 33,  9, 41],
        [51, 19, 59, 27, 49, 17, 57, 25],
        [15, 47,  7, 39, 13, 45,  5, 37],
        [63, 31, 55, 23, 61, 29, 53, 21],
    ]),
}


class Dither(NodeBase):
    """Binary (black/white) dithering with a configurable algorithm.

    Reduces an image to two levels (0 / 255) using one of the classic
    ordered or error-diffusion schemes. Inputs can be single- or
    three-channel — colour inputs are converted to grayscale first and
    the binary result is re-broadcast to BGR so downstream nodes get
    the expected 3-channel format. Ported from the original OCVL
    ``DitherProcessor``; the ``numba`` JIT dependency is dropped so the
    error-diffusion loop runs in pure Python / NumPy.
    """

    def __init__(self) -> None:
        super().__init__("Dither")
        self._method: int = int(DitherMethod.STUCKI)

        self._add_input(InputPort("image", {IoDataType.IMAGE}))
        self._add_output(OutputPort("image", {IoDataType.IMAGE}))

        self._apply_default_params()

    # ── Parameters ─────────────────────────────────────────────────────────────

    @property
    @override
    def params(self) -> list[NodeParam]:
        # Method is encoded as an int: see :class:`DitherMethod`.
        # 1=Bayer2  2=Bayer4  3=Bayer8  4=Noise  5=Floyd-Steinberg
        # 6=Stucki  7=Atkinson 8=Burkes 9=Sierra 10=DiffusionX 11=DiffusionXY
        return [NodeParam("method", NodeParamType.INT, {"default": int(DitherMethod.STUCKI)})]

    # ── Properties ─────────────────────────────────────────────────────────────

    @property
    def method(self) -> int:
        return self._method

    @method.setter
    def method(self, value: int) -> None:
        v = int(value)
        try:
            DitherMethod(v)
        except ValueError as e:
            raise ValueError(
                f"method must be one of {[m.value for m in DitherMethod]} (got {v})"
            ) from e
        self._method = v

    # ── NodeBase interface ─────────────────────────────────────────────────────

    @override
    def process(self) -> None:
        image: np.ndarray = self.inputs[0].data.image

        if image.ndim == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image

        method = DitherMethod(self._method)
        if method == DitherMethod.NOISE:
            out = _dither_noise(gray)
        elif method in _BAYER_MATRICES:
            out = _dither_bayer(gray, _BAYER_MATRICES[method])
        else:
            out = _dither_diffusion(gray, _DIFFUSION_KERNELS[method])

        out_bgr = cv2.cvtColor(out, cv2.COLOR_GRAY2BGR)
        self.outputs[0].send(IoData.from_image(out_bgr))


# ── Dithering kernels ─────────────────────────────────────────────────────────

def _dither_noise(gray: np.ndarray) -> np.ndarray:
    """Threshold against Gaussian noise (μ=128, σ=50). Matches the OCVL
    implementation — ``cv2.randn`` fills the noise image in place."""
    noise = np.zeros_like(gray)
    cv2.randn(noise, 128, 50)
    return np.where(gray > noise, 255, 0).astype(np.uint8)


def _dither_bayer(gray: np.ndarray, bayer: np.ndarray) -> np.ndarray:
    """Ordered dither using a Bayer matrix.

    Replaces the original nested-loop implementation with a vectorised
    threshold — the matrix is tiled across the frame and each pixel is
    compared against its threshold in one NumPy expression. The levels
    branch in the OCVL code computed ``new_pixel`` but never used it,
    so it is omitted here.
    """
    h, w = gray.shape
    side = int(math.sqrt(bayer.size))
    div = bayer.size
    reps = (h // side + 1, w // side + 1)
    tiled = np.tile(bayer, reps)[:h, :w]
    threshold = tiled * 255 / div
    return np.where(gray > threshold, 255, 0).astype(np.uint8)


def _dither_diffusion(
    gray: np.ndarray,
    kernel: tuple[tuple[int, int, float], ...],
) -> np.ndarray:
    """Generic error-diffusion dither.

    Walks the image in scanline order, quantising each pixel to 0 or
    255 and distributing the quantisation error to the neighbours
    listed in ``kernel`` as ``(dy, dx, weight)`` triples. Works on a
    float copy so accumulated error stays in range before the final
    clip. Pure-Python loop: without numba this is slow on large
    frames, but produces identical output.
    """
    buf = gray.astype(np.float32).copy()
    h, w = buf.shape

    for y in range(h):
        for x in range(w):
            old = buf[y, x]
            new = 255.0 if old > 127 else 0.0
            buf[y, x] = new
            err = old - new
            if err == 0.0:
                continue
            for dy, dx, weight in kernel:
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w:
                    buf[ny, nx] += err * weight

    return np.clip(buf, 0, 255).astype(np.uint8)
