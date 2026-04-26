from __future__ import annotations

import numpy as np
from typing_extensions import override

from core.io_data import IoData, IoDataType
from core.node_base import NodeBase
from core.port import InputPort, OutputPort


class Fft2D(NodeBase):
    """Compute the 2-D discrete Fourier transform of a greyscale image.

    Outputs:

    * ``spectrum`` — the full complex spectrum as a 2-D
      :data:`IoDataType.MATRIX` (``np.complex128``), with the DC
      component shifted to the centre via :func:`numpy.fft.fftshift`.
      Designed to be wired into :class:`InverseFft2D` (which undoes
      both the shift and the transform) for a pixel-exact round trip.
    * ``magnitude`` — a log-scaled magnitude spectrum normalised to
      ``[0, 255]`` and emitted as a uint8
      :data:`IoDataType.IMAGE_GREY` for direct previewing through a
      Display node. Computed as
      ``log1p(|spectrum|)`` so the bright DC peak does not crush the
      surrounding harmonics into black.

    Single-channel (greyscale) input only — a colour image must be
    split with :class:`HsvSplit` / :class:`RgbaSplit` /
    :class:`Grayscale` first.
    """

    def __init__(self) -> None:
        super().__init__("FFT 2D", section="Frequency")
        self._add_input(InputPort("image", {IoDataType.IMAGE_GREY}))
        self._add_output(OutputPort("spectrum", {IoDataType.MATRIX}))
        self._add_output(OutputPort("magnitude", {IoDataType.IMAGE_GREY}))

    @override
    def process_impl(self) -> None:
        image: np.ndarray = self.inputs[0].data.image
        if image.ndim != 2:
            raise ValueError(
                f"Fft2D expects a single-channel image, got shape {image.shape}"
            )

        spectrum = np.fft.fftshift(np.fft.fft2(image.astype(np.float64)))

        magnitude = np.log1p(np.abs(spectrum))
        peak = float(magnitude.max())
        if peak > 0.0:
            magnitude = (magnitude * (255.0 / peak))
        magnitude_u8 = magnitude.astype(np.uint8, copy=False)

        self.outputs[0].send(IoData.from_matrix(spectrum))
        self.outputs[1].send(IoData.from_greyscale(magnitude_u8))
