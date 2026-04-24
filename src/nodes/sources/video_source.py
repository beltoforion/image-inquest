from __future__ import annotations

import sys
from pathlib import Path

import cv2
from typing_extensions import override

from constants import INPUT_DIR
from core.io_data import IoData, IoDataType
from core.node_base import SourceNodeBase, NodeParam, NodeParamType
from core.port import OutputPort

_SUPPORTED_EXTS = {".mp4", ".avi", ".mov", ".mkv"}


def _win_safe_path(path: Path) -> str:
    """Return an ASCII-safe path for cv2 on Windows.

    cv2.VideoCapture uses C-runtime narrow-string file I/O on Windows and
    silently fails for paths containing non-ASCII characters.  The Windows
    8.3 short path is always ASCII, so we use GetShortPathNameW when running
    on Windows and fall back to the original string on all other platforms.
    """
    if sys.platform != "win32":
        return str(path)
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(32768)
        if ctypes.windll.kernel32.GetShortPathNameW(str(path), buf, len(buf)):  # type: ignore[attr-defined]
            return buf.value
    except Exception:
        pass
    return str(path)


class VideoSource(SourceNodeBase):
    """Source node that reads video frames from a file.

    Supported formats: MP4, AVI, MOV, MKV.

    Unlike :class:`ImageSource`, this source is **not** reactive — the flow
    only runs when the Run button is pressed.  This avoids restarting a
    potentially long video decode on every keystroke.

    Parameters:
      file_path      -- path to the input video file
      max_num_frames -- maximum number of frames to decode (-1 = all)
    """

    def __init__(self) -> None:
        super().__init__("Video Source", section="Sources")
        self._file_path: Path = Path()
        self._max_num_frames: int = -1
        self._add_output(OutputPort("image", {IoDataType.IMAGE}))
        self._apply_default_params()

    # ── Parameters ─────────────────────────────────────────────────────────────

    @property
    @override
    def params(self) -> list[NodeParam]:
        return [
            NodeParam("file_path",      NodeParamType.FILE_PATH, {"default": "./input/example.mp4", "filter": "Video (*.mp4 *.avi *.mov *.mkv)", "base_dir": INPUT_DIR}),
            NodeParam("max_num_frames", NodeParamType.INT,       {"default": -1}),
        ]

    @property
    def file_path(self) -> Path:
        return self._file_path

    @file_path.setter
    def file_path(self, path: str | Path) -> None:
        self._file_path = Path(path)

    @property
    def max_num_frames(self) -> int:
        return self._max_num_frames

    @max_num_frames.setter
    def max_num_frames(self, value: int) -> None:
        self._max_num_frames = int(value)

    # ── SourceNodeBase interface ────────────────────────────────────────────────

    @override
    def process_impl(self) -> None:
        if not self._file_path.exists():
            raise FileNotFoundError(f"Input file not found: {self._file_path}")

        ext = self._file_path.suffix.lower()
        if ext not in _SUPPORTED_EXTS:
            raise ValueError(
                f"Unsupported file type '{ext}'. "
                f"Supported: {_SUPPORTED_EXTS}"
            )

        cap = cv2.VideoCapture(_win_safe_path(self._file_path))
        try:
            frame_count = 0
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                self.outputs[0].send(IoData.from_image(frame))
                frame_count += 1
                if self._max_num_frames >= 0 and frame_count >= self._max_num_frames:
                    break
        finally:
            cap.release()
