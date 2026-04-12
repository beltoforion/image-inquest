from __future__ import annotations

from typing import TYPE_CHECKING

import dearpygui.dearpygui as dpg

from core.flow import Flow
from core.node_base import NodeBase
from nodes.sources.file_source import FileSource
from ui.page import Page

if TYPE_CHECKING:
    from ui.page_manager import PageManager


class NodeEditorPage(Page):
    name = "editor"

    def __init__(self, parent: int | str, menu_bar: int | str, page_manager: PageManager) -> None:
        self._node_editor_tag: int | str = dpg.generate_uuid()
        self._flow: Flow | None = None
        super().__init__(parent=parent, menu_bar=menu_bar, page_manager=page_manager)

    def set_flow(self, flow: Flow) -> None:
        self._flow = flow

    def _build_ui(self) -> None:
        dpg.add_spacer(height=20)
        with dpg.group(horizontal=True):
            dpg.add_button(label="Add Node", callback=self._on_add_node)
            dpg.add_button(label="Clear All", callback=self._on_clear_nodes)
        dpg.add_node_editor(
            tag=self._node_editor_tag,
            callback=self._link,
            delink_callback=self._delink,
            height=-1,
        )

    def _install_menus(self) -> None:
        menu_tag = dpg.generate_uuid()
        with dpg.menu(label="Node Editor", parent=self._menu_bar, tag=menu_tag):
            dpg.add_menu_item(label="Add Node", callback=self._on_add_node)
            dpg.add_menu_item(label="Clear All", callback=self._on_clear_nodes)
            dpg.add_separator()
            dpg.add_menu_item(label="Exit", callback=self._on_exit_clicked)
        self._menu_tags.append(menu_tag)

    # ── Node creation ──────────────────────────────────────────────────────────

    def _add_visual_node(self, node: NodeBase) -> None:
        """Create a visual node in the editor reflecting the node's ports."""
        with dpg.node(label=node.display_name, parent=self._node_editor_tag):
            for port in node.inputs:
                with dpg.node_attribute(label=port.name):
                    dpg.add_text(", ".join(t.value for t in port.accepted_types))
            for port in node.outputs:
                with dpg.node_attribute(label=port.name, attribute_type=dpg.mvNode_Attr_Output):
                    dpg.add_text(", ".join(t.value for t in port.emits))

    # ── Link callbacks ─────────────────────────────────────────────────────────

    def _link(self, sender, app_data) -> None:
        dpg.add_node_link(app_data[0], app_data[1], parent=sender)

    def _delink(self, sender, app_data) -> None:
        dpg.delete_item(app_data)

    # ── Clear ──────────────────────────────────────────────────────────────────

    def _clear_nodes(self) -> None:
        children = dpg.get_item_children(self._node_editor_tag, 1)
        if children:
            for child in children:
                dpg.delete_item(child)
        if self._flow is not None:
            for node in list(self._flow.nodes):
                self._flow.remove_node(node)

    # ── Button / menu callbacks ────────────────────────────────────────────────

    def _on_add_node(self, sender=None) -> None:
        node = FileSource()
        if self._flow is not None:
            self._flow.add_node(node)
        self._add_visual_node(node)

    def _on_clear_nodes(self, sender=None) -> None:
        self._clear_nodes()

    def _on_exit_clicked(self, sender=None) -> None:
        self._clear_nodes()
        self._page_manager.activate(self._page_manager.start_page)
