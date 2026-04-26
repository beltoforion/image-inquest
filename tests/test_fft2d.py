"""Unit tests for the 2-D FFT and inverse FFT filters."""
from __future__ import annotations

import numpy as np

from core.io_data import IoData, IoDataType
from core.port import InputPort
from nodes.filters.fft2d import Fft2D
from nodes.filters.inverse_fft2d import InverseFft2D


# ── Fft2D ──────────────────────────────────────────────────────────────────────

def test_fft2d_emits_complex_spectrum_and_grey_magnitude() -> None:
    node = Fft2D()
    image = np.arange(64, dtype=np.uint8).reshape(8, 8)
    node.inputs[0].receive(IoData.from_greyscale(image))

    spectrum = node.outputs[0].last_emitted
    magnitude = node.outputs[1].last_emitted
    assert spectrum is not None and spectrum.type == IoDataType.MATRIX
    assert magnitude is not None and magnitude.type == IoDataType.IMAGE_GREY
    assert spectrum.payload.shape == (8, 8)
    assert np.iscomplexobj(spectrum.payload)
    assert magnitude.image.shape == (8, 8)
    assert magnitude.image.dtype == np.uint8


def test_fft2d_dc_at_centre_for_constant_image() -> None:
    """A constant image's spectrum has a single non-zero coefficient at
    the DC bin; with fftshift that bin is the centre of the matrix."""
    node = Fft2D()
    image = np.full((8, 8), 42, dtype=np.uint8)
    node.inputs[0].receive(IoData.from_greyscale(image))

    spectrum = node.outputs[0].last_emitted.payload
    centre = spectrum[4, 4]  # fftshift puts DC at (N//2, N//2)
    energy = np.abs(spectrum)
    energy[4, 4] = 0
    assert abs(centre) > 0
    assert np.allclose(energy, 0)


def test_fft2d_rejects_colour_input_at_process_time() -> None:
    node = Fft2D()
    bgr = np.zeros((4, 4, 3), dtype=np.uint8)
    # Receive doesn't validate ndim — only the process_impl does. Force
    # the dispatcher to fire and assert that the failure surfaces there.
    try:
        node.inputs[0].receive(IoData.from_greyscale(bgr))
    except Exception as exc:
        assert "single-channel" in str(exc)
    else:
        raise AssertionError("Fft2D must reject 3-D input")


# ── Round-trip ─────────────────────────────────────────────────────────────────

def test_fft_ifft_roundtrip_is_pixel_exact() -> None:
    """Fft2D → InverseFft2D must reproduce a uint8 greyscale input."""
    fft = Fft2D()
    ifft = InverseFft2D()
    fft.outputs[0].connect(ifft.inputs[0])  # spectrum → spectrum

    capture = InputPort("cap", {IoDataType.IMAGE_GREY})
    ifft.outputs[0].connect(capture)

    rng = np.random.default_rng(0)
    original = rng.integers(0, 256, size=(16, 16), dtype=np.uint8)
    fft.inputs[0].receive(IoData.from_greyscale(original))

    assert capture.has_data
    np.testing.assert_array_equal(capture.data.image, original)


def test_fft_ifft_lowpass_filtering_preserves_shape_and_range() -> None:
    """Zeroing the high-frequency corners must still produce a valid
    uint8 greyscale image (same shape, dtype, in-range values)."""
    fft = Fft2D()
    ifft = InverseFft2D()

    image = (np.arange(256, dtype=np.uint8).reshape(16, 16))
    fft.inputs[0].receive(IoData.from_greyscale(image))

    spectrum = fft.outputs[0].last_emitted.payload.copy()
    mask = np.zeros_like(spectrum, dtype=bool)
    mask[4:12, 4:12] = True
    spectrum[~mask] = 0

    ifft.inputs[0].receive(IoData.from_matrix(spectrum))
    out = ifft.outputs[0].last_emitted
    assert out is not None and out.type == IoDataType.IMAGE_GREY
    assert out.image.shape == (16, 16)
    assert out.image.dtype == np.uint8
