from __future__ import annotations

import cv2
from typing_extensions import override

from core.io_data import IoData, IoDataType
from core.node_base import NodeBase
from core.port import InputPort, OutputPort


class HslJoin(NodeBase):
    """Merge three single-channel images (H, S, L) into a BGR image.

    Inverse of :class:`HslSplit`. The three planes are stacked into an
    ``H × W × 3`` HLS image (full-range hue, 0..255) and converted via
    :data:`cv2.COLOR_HLS2BGR_FULL` so that
    ``HslSplit → HslJoin`` is a pixel-exact identity on a BGR input.

    The input ports are labelled ``H``, ``S``, ``L`` to match the
    conventional HSL ordering users expect; internally the planes are
    re-ordered to OpenCV's H, L, S layout before
    :func:`cv2.cvtColor`.
    """

    def __init__(self) -> None:
        super().__init__("HSL Join", section="Color Spaces")
        self._add_input(InputPort("H", {IoDataType.IMAGE_GREY}))
        self._add_input(InputPort("S", {IoDataType.IMAGE_GREY}))
        self._add_input(InputPort("L", {IoDataType.IMAGE_GREY}))
        self._add_output(OutputPort("image", {IoDataType.IMAGE}))

    @override
    def process_impl(self) -> None:
        h = self.inputs[0].data.image
        s = self.inputs[1].data.image
        l = self.inputs[2].data.image
        hls = cv2.merge((h, l, s))
        bgr = cv2.cvtColor(hls, cv2.COLOR_HLS2BGR_FULL)
        self.outputs[0].send(IoData.from_image(bgr))
