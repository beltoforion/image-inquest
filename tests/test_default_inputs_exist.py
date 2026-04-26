"""Regression test: every read-side source node's file-path default must
resolve to a file that actually ships under INPUT_DIR.

Fixes Issue #173 — ImageSource used "example.jpg" which was never bundled.
"""
from __future__ import annotations

import pytest

from constants import INPUT_DIR
from core.path_utils import resolve_against
from nodes.sources.image_source import ImageSource
from nodes.sources.video_source import VideoSource


@pytest.mark.parametrize("node_cls,attr", [
    (ImageSource, "file_path"),
    (VideoSource, "file_path"),
])
def test_source_default_resolves(node_cls: type, attr: str) -> None:
    node = node_cls()
    default = getattr(node, attr)
    resolved = resolve_against(default, INPUT_DIR)
    assert resolved.exists(), (
        f"{node_cls.__name__}.{attr} default {str(default)!r} does not exist "
        f"under INPUT_DIR ({INPUT_DIR})"
    )
