from __future__ import annotations

import cv2
import numpy as np
from typing_extensions import override

from core.io_data import IoData, IoDataType
from core.node_base import NodeBase, NodeParam, NodeParamType
from core.port import InputPort, OutputPort


class Ncc(NodeBase):
    """Normalised cross-correlation template matching.

    Wraps ``cv2.matchTemplate`` with ``TM_CCORR_NORMED`` and rescales the
    score map to a ``uint8`` greyscale image. The ``template`` input is
    the pattern searched for within ``image``. Both inputs must be
    single-channel greyscale. Ported from the original OCVL
    ``NccProcessor``.

    With ``retain_size=True`` (default) the match map is pasted into a
    canvas the same size as ``image`` and offset by half the template
    size, so each response sits at the pixel it corresponds to (template
    centre). With ``retain_size=False`` the raw ``matchTemplate`` output
    is emitted, which is smaller than the input by ``template.shape - 1``
    on each axis.

    Multi-input EOS handling: ``Flow.run`` drives sources serially, so
    one upstream chain can deliver its data *and* EOS before the other
    has emitted anything. The default dispatcher would see EOS on one
    input paired with real data on the other and take the
    :meth:`_on_end_of_stream` branch — skipping the match entirely. This
    node overrides :meth:`_signal_input_ready` to latch the last real
    frame on each input and only forward EOS once every input has seen
    it, so processing runs whenever both image and template are
    available even if one upstream finished first.
    """

    _IMAGE_IDX = 0
    _TEMPLATE_IDX = 1

    def __init__(self) -> None:
        super().__init__("NCC", section="Processing")
        self._retain_size: bool = True

        self._add_input(InputPort("image", {IoDataType.IMAGE_GREY}))
        self._add_input(InputPort("template", {IoDataType.IMAGE_GREY}))
        self._add_output(OutputPort("image", {IoDataType.IMAGE_GREY}))

        self._latched: list[np.ndarray | None] = [None, None]
        self._eos_seen: list[bool] = [False, False]
        self._eos_forwarded: bool = False

        self._apply_default_params()

    # ── Parameters ─────────────────────────────────────────────────────────────

    @property
    @override
    def params(self) -> list[NodeParam]:
        return [NodeParam("retain_size", NodeParamType.BOOL, {"default": True})]

    # ── Properties ─────────────────────────────────────────────────────────────

    @property
    def retain_size(self) -> bool:
        return self._retain_size

    @retain_size.setter
    def retain_size(self, value: bool) -> None:
        self._retain_size = bool(value)

    # ── NodeBase interface ─────────────────────────────────────────────────────

    @override
    def _before_run_impl(self) -> None:
        super()._before_run_impl()
        self._latched = [None, None]
        self._eos_seen = [False, False]
        self._eos_forwarded = False

    @override
    def _signal_input_ready(self) -> None:
        new_frame = False
        for idx, port in enumerate(self._inputs):
            if not port.has_data:
                continue
            data = port.data
            port.clear()
            if data.is_end_of_stream():
                self._eos_seen[idx] = True
            else:
                self._latched[idx] = data.image
                new_frame = True

        if new_frame and all(img is not None for img in self._latched):
            self.process()

        if not self._eos_forwarded and all(self._eos_seen):
            self._eos_forwarded = True
            eos = IoData.end_of_stream()
            for out in self._outputs:
                out.send(eos)

    @override
    def process_impl(self) -> None:
        image = self._latched[self._IMAGE_IDX]
        template = self._latched[self._TEMPLATE_IDX]
        assert image is not None and template is not None  # guarded by _signal_input_ready

        res = cv2.matchTemplate(image, template, cv2.TM_CCORR_NORMED)
        res = cv2.normalize(
            (res * 255).astype(np.uint8),
            None,
            alpha=0,
            beta=255,
            norm_type=cv2.NORM_MINMAX,
        )

        if self._retain_size:
            h_t, w_t = template.shape[:2]
            h_orig, w_orig = image.shape[:2]
            h_m, w_m = res.shape[:2]

            y0 = h_t // 2
            x0 = w_t // 2

            canvas = np.zeros((h_orig, w_orig), dtype=np.uint8)
            canvas[y0:y0 + h_m, x0:x0 + w_m] = res
            out = canvas
        else:
            out = res

        self.outputs[0].send(IoData.from_greyscale(out))
