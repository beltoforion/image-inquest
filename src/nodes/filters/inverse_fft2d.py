from __future__ import annotations

import numpy as np
from typing_extensions import override

from core.io_data import IoData, IoDataType
from core.node_base import NodeBase
from core.port import InputPort, OutputPort


class InverseFft2D(NodeBase):
    """Compute the inverse 2-D discrete Fourier transform.

    Inverse of :class:`Fft2D`. Expects an fftshifted complex spectrum
    on the ``spectrum`` input (the format :class:`Fft2D` emits) and
    emits a uint8 :data:`IoDataType.IMAGE_GREY` on ``image``.

    The reconstruction takes the real part of :func:`numpy.fft.ifft2`
    (the imaginary part is at numerical-noise level for a spectrum
    that came from a real-valued image, possibly modulated by a
    real-valued mask), rounds to the nearest integer, clips to
    ``[0, 255]`` and casts to ``uint8`` so the result composes
    cleanly with the rest of the image-processing graph. The explicit
    :func:`numpy.round` step is what makes ``Fft2D → InverseFft2D`` a
    pixel-exact identity on a greyscale uint8 input — without it,
    sub-ULP float drift from the forward+inverse transform would
    truncate values like ``15 - 1e-13`` to ``14`` on the cast.
    """

    def __init__(self) -> None:
        super().__init__("Inverse FFT 2D", section="Frequency")
        self._add_input(InputPort("spectrum", {IoDataType.MATRIX}))
        self._add_output(OutputPort("image", {IoDataType.IMAGE_GREY}))

    @override
    def process_impl(self) -> None:
        spectrum: np.ndarray = self.inputs[0].data.payload
        if spectrum.ndim != 2:
            raise ValueError(
                f"InverseFft2D expects a 2-D spectrum, got shape {spectrum.shape}"
            )

        recon = np.fft.ifft2(np.fft.ifftshift(spectrum)).real
        np.round(recon, out=recon)
        np.clip(recon, 0.0, 255.0, out=recon)
        image = recon.astype(np.uint8, copy=False)
        self.outputs[0].send(IoData.from_greyscale(image))
