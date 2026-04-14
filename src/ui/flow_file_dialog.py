from __future__ import annotations

from typing import Callable

import dearpygui.dearpygui as dpg

from ui._types import DpgTag

#: Extension used for saved flow files. Centralised so Save, the Open
#: dialog filter, and any future importers stay in sync.
FLOW_FILE_EXTENSION: str = ".flowjs"


def make_open_flow_dialog(tag: DpgTag, callback: Callable[..., None]) -> None:
    """Create a persistent, initially-hidden DPG file dialog for picking a flow.

    The dialog is filtered to :data:`FLOW_FILE_EXTENSION`. The caller is
    responsible for showing it (``dpg.show_item(tag)``) and for setting
    ``default_path`` to the desired starting directory before doing so.
    """
    with dpg.file_dialog(
        label="Open Flow",
        tag=tag,
        callback=callback,
        show=False,
        modal=True,
        width=700,
        height=400,
    ):
        dpg.add_file_extension(FLOW_FILE_EXTENSION, color=(0, 200, 255, 255), custom_text="Flow")
