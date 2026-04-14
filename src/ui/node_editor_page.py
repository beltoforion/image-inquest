from __future__ import annotations

import importlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Literal

import dearpygui.dearpygui as dpg
from typing_extensions import override

from constants import FLOW_DIR
from core.flow import Flow
from core.node_base import NodeBase
from core.node_registry import NodeEntry, NodeRegistry
from ui._types import DpgTag
from ui.dpg_node_builder import DpgNodeBuilder
from ui.dpg_node_list_builder import DpgNodeListBuilder
from ui.page import Page

_FLOW_FORMAT_VERSION = 1
_PortKind = Literal["input", "output"]

_SAVE_OK_COLOR   = ( 90, 200, 100, 255)
_SAVE_FAIL_COLOR = (220,  80,  80, 255)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ui.dpg_themes import DpgThemes
    from ui.page_manager import PageManager


class NodeEditorPage(Page):
    name: str = "editor"

    def __init__(
        self,
        parent: DpgTag,
        menu_bar: DpgTag,
        page_manager: PageManager,
        registry: NodeRegistry,
        themes: DpgThemes,
    ) -> None:
        self._node_editor_tag: DpgTag = dpg.generate_uuid()
        self._canvas_tag:      DpgTag = dpg.generate_uuid()
        self._save_status_tag: DpgTag = dpg.generate_uuid()
        self._flow:     Flow | None    = None
        self._registry: NodeRegistry    = registry
        self._node_builder: DpgNodeBuilder = DpgNodeBuilder(self._node_editor_tag, themes)

        # Node tracking for delete / context-menu / save support
        self._node_map:        dict[DpgTag, NodeBase]       = {}
        self._node_dialog_map: dict[DpgTag, DpgTag | None]  = {}
        self._attr_to_port:    dict[DpgTag, tuple[NodeBase, _PortKind, int]] = {}
        self._ctx_target:      tuple[DpgTag, NodeBase] | None = None
        self._ctx_links:       list[DpgTag]                 = []

        # Context-menu window tags (windows populated in _build_ui)
        self._node_ctx_tag: DpgTag = dpg.generate_uuid()
        self._link_ctx_tag: DpgTag = dpg.generate_uuid()
        super().__init__(parent=parent, menu_bar=menu_bar, page_manager=page_manager, themes=themes)

    def set_flow(self, flow: Flow) -> None:
        self._flow = flow

    # ── UI construction ────────────────────────────────────────────────────────

    @override
    def _build_ui(self) -> None:
        self._build_ctx_menu(self._node_ctx_tag, "Delete Node", self._on_ctx_delete_node)
        self._build_ctx_menu(self._link_ctx_tag, "Delete Connection(s)", self._delete_selected_links)

        with dpg.handler_registry():
            dpg.add_mouse_click_handler(button=dpg.mvMouseButton_Right, callback=self._on_right_click)
            dpg.add_mouse_click_handler(button=dpg.mvMouseButton_Left,  callback=self._on_left_click)

        dpg.add_spacer(height=20)
        with dpg.group(horizontal=True):
            DpgNodeListBuilder(self._registry)
            with dpg.group():
                with dpg.group(horizontal=True):
                    dpg.add_button(label="Save",      callback=self._save_flow)
                    dpg.add_button(label="Clear All", callback=self._clear_nodes)
                    dpg.add_spacer(width=16)
                    # Status readout updated by _save_flow. Empty until the
                    # first save attempt.
                    dpg.add_text("", tag=self._save_status_tag)

                with dpg.child_window(
                    tag=self._canvas_tag,
                    drop_callback=self._on_node_dropped,
                    payload_type=DpgNodeListBuilder.PAYLOAD_TYPE,
                    width=-1,
                    height=-1,
                    border=False):
                    dpg.add_node_editor(
                        tag=self._node_editor_tag,
                        callback=self._link,
                        delink_callback=self._delink,
                        width=-1,
                        height=-1)

    @staticmethod
    def _build_ctx_menu(tag: DpgTag, item_label: str, callback: Callable[..., None]) -> None:
        with dpg.window(
            tag=tag,
            show=False,
            no_title_bar=True,
            autosize=True,
            no_scrollbar=True,
            no_move=True,
            no_resize=True,
            no_collapse=True,
            min_size=(10, 10),
        ):
            dpg.add_menu_item(label=item_label, callback=callback)

    # ── Node creation ──────────────────────────────────────────────────────────

    def _on_node_dropped(self, sender: DpgTag, app_data: NodeEntry) -> None:
        module = importlib.import_module(app_data.module)
        cls = getattr(module, app_data.class_name)
        node: NodeBase = cls()
        logger.debug("Adding node '%s'", node.display_name)

        if self._flow is not None:
            self._flow.add_node(node)

        node_tag = self._add_visual_node(node)
        mouse_pos  = dpg.get_mouse_pos(local=True)
        canvas_pos = dpg.get_item_pos(self._canvas_tag)
        dpg.set_item_pos(node_tag, [
            mouse_pos[0] - canvas_pos[0],
            mouse_pos[1] - canvas_pos[1],
        ])

    def _add_visual_node(self, node: NodeBase) -> DpgTag:
        node_tag, dialog_tag = self._node_builder.build(node)
        self._node_map[node_tag] = node
        self._node_dialog_map[node_tag] = dialog_tag
        self._index_node_attrs(node_tag, node)
        return node_tag

    def _index_node_attrs(self, node_tag: DpgTag, node: NodeBase) -> None:
        """Record the mapping from each port's DPG attribute tag to
        ``(node, 'input'|'output', port_index)``.

        DpgNodeBuilder creates node_attribute children in this order:
        one per NodeParam (static), then one per input port, then one
        per output port. We rely on that order to resolve attribute
        tags back to ports at save time.
        """
        children = dpg.get_item_children(node_tag, 1) or []
        offset = len(node.params)
        for i in range(len(node.inputs)):
            self._attr_to_port[children[offset + i]] = (node, "input", i)
        offset += len(node.inputs)
        for i in range(len(node.outputs)):
            self._attr_to_port[children[offset + i]] = (node, "output", i)

    # ── Right-click / context menus ────────────────────────────────────────────

    def _on_right_click(self) -> None:
        """Show the appropriate context menu on right-click inside the editor."""
        if not self._active:
            return

        for tag, node in self._node_map.items():
            if dpg.does_item_exist(tag) and dpg.get_item_state(tag).get("hovered", False):
                self._ctx_target = (tag, node)
                self._hide_ctx_menus()
                dpg.set_item_pos(self._node_ctx_tag, dpg.get_mouse_pos())
                dpg.configure_item(self._node_ctx_tag, show=True)
                return

        self._ctx_links = dpg.get_selected_links(self._node_editor_tag)
        if not self._ctx_links:
            return
        self._hide_ctx_menus()
        dpg.set_item_pos(self._link_ctx_tag, dpg.get_mouse_pos())
        dpg.configure_item(self._link_ctx_tag, show=True)

    def _on_left_click(self) -> None:
        """Dismiss context menus when clicking outside them."""
        if not self._active:
            return
        for tag in (self._node_ctx_tag, self._link_ctx_tag):
            if dpg.does_item_exist(tag) and not dpg.get_item_state(tag).get("hovered", False):
                dpg.configure_item(tag, show=False)

    def _hide_ctx_menus(self) -> None:
        dpg.configure_item(self._node_ctx_tag, show=False)
        dpg.configure_item(self._link_ctx_tag, show=False)

    def _on_ctx_delete_node(self) -> None:
        dpg.configure_item(self._node_ctx_tag, show=False)
        if self._ctx_target is not None:
            self._delete_node(*self._ctx_target)
            self._ctx_target = None

    def _delete_node(self, node_tag: DpgTag, node: NodeBase) -> None:
        """Remove a node and all its connected links from the canvas and flow."""
        attr_tags = set(dpg.get_item_children(node_tag, 1) or [])

        # Links live in slot 0 of the node editor; scan only those.
        for link_tag in list(dpg.get_item_children(self._node_editor_tag, 0) or []):
            try:
                conf = dpg.get_item_configuration(link_tag)
            except SystemError:
                # Link may have been deleted mid-iteration (e.g. by DPG auto-cleanup).
                logger.debug("Skipped link %s while deleting node", link_tag, exc_info=True)
                continue
            if conf.get("attr_1") in attr_tags or conf.get("attr_2") in attr_tags:
                dpg.delete_item(link_tag)

        for attr_tag in attr_tags:
            self._attr_to_port.pop(attr_tag, None)

        dialog_tag = self._node_dialog_map.pop(node_tag, None)
        if dialog_tag is not None and dpg.does_item_exist(dialog_tag):
            dpg.delete_item(dialog_tag)

        self._node_map.pop(node_tag, None)
        if dpg.does_item_exist(node_tag):
            dpg.delete_item(node_tag)
        logger.debug("Deleted node '%s'", node.display_name)

        if self._flow is not None:
            self._flow.remove_node(node)

    def _delete_selected_links(self) -> None:
        """Delete the links that were selected when the context menu was opened."""
        dpg.configure_item(self._link_ctx_tag, show=False)
        for link in self._ctx_links:
            if dpg.does_item_exist(link):
                dpg.delete_item(link)
        self._ctx_links = []

    # ── Link callbacks ─────────────────────────────────────────────────────────

    def _link(self, sender: DpgTag, app_data: tuple[DpgTag, DpgTag]) -> None:
        link_tag = dpg.add_node_link(app_data[0], app_data[1], parent=sender)
        self._themes.apply_to_link(link_tag)

    def _delink(self, sender: DpgTag, app_data: DpgTag) -> None:
        dpg.delete_item(app_data)

    # ── Clear ──────────────────────────────────────────────────────────────────

    def _clear_nodes(self, *_: object) -> None:
        for node_tag, node in list(self._node_map.items()):
            self._delete_node(node_tag, node)

        self._ctx_target = None
        self._ctx_links = []

    # ── Menu ───────────────────────────────────────────────────────────────────

    @override
    def _install_menus(self) -> None:
        menu_tag = dpg.generate_uuid()
        label = f"Node Editor [{self._flow.name}]" if self._flow is not None else "Node Editor"
        with dpg.menu(label=label, parent=self._menu_bar, tag=menu_tag):
            dpg.add_menu_item(label="Save",      callback=self._save_flow)
            dpg.add_menu_item(label="Clear All", callback=self._clear_nodes)
            dpg.add_separator()
            dpg.add_menu_item(label="Exit", callback=self._on_exit_clicked)
        self._menu_tags.append(menu_tag)

    # ── Save ───────────────────────────────────────────────────────────────────

    def _save_flow(self, *_: object) -> None:
        if self._flow is None:
            logger.warning("Save requested but no flow is active")
            self._set_save_status("No flow to save", _SAVE_FAIL_COLOR)
            return
        data = self._serialize_flow(self._flow)
        try:
            FLOW_DIR.mkdir(parents=True, exist_ok=True)
            path = FLOW_DIR / f"{self._flow.name}.json"
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError as err:
            logger.exception("Failed to save flow '%s'", self._flow.name)
            self._set_save_status(f"Save failed ({err.strerror or err.__class__.__name__})",
                                  _SAVE_FAIL_COLOR)
            return
        logger.info("Saved flow to %s", path)
        self._set_save_status(
            f"Saved to {self._display_path(path)} at {datetime.now().strftime('%H:%M:%S')}",
            _SAVE_OK_COLOR,
        )

    def _set_save_status(self, message: str, color: tuple[int, int, int, int]) -> None:
        """Update the Save-status readout below the button row."""
        if not dpg.does_item_exist(self._save_status_tag):
            return
        dpg.set_value(self._save_status_tag, message)
        dpg.configure_item(self._save_status_tag, color=color)

    @staticmethod
    def _display_path(path: Path) -> str:
        """Return ``path`` relative to the current working directory when
        possible, otherwise the absolute path. Keeps the status line short."""
        try:
            return str(path.relative_to(Path.cwd()))
        except ValueError:
            return str(path)

    def _serialize_flow(self, flow: Flow) -> dict:
        """Return a JSON-compatible dict snapshot of the current editor state."""
        nodes_in_order = list(self._node_map.items())  # insertion order == creation order
        node_ids: dict[int, int] = {id(node): idx for idx, (_, node) in enumerate(nodes_in_order)}

        nodes_out = [self._node_to_dict(i, tag, node) for i, (tag, node) in enumerate(nodes_in_order)]
        connections_out = self._connections_to_list(node_ids)

        return {
            "version":     _FLOW_FORMAT_VERSION,
            "name":        flow.name,
            "nodes":       nodes_out,
            "connections": connections_out,
        }

    def _node_to_dict(self, node_id: int, node_tag: DpgTag, node: NodeBase) -> dict:
        pos = dpg.get_item_pos(node_tag)
        params = {p.name: _jsonable(getattr(node, p.name, None)) for p in node.params}
        return {
            "id":       node_id,
            "module":   type(node).__module__,
            "class":    type(node).__name__,
            "position": [float(pos[0]), float(pos[1])],
            "params":   params,
        }

    def _connections_to_list(self, node_ids: dict[int, int]) -> list[dict]:
        """Derive connections from the DPG node_editor's visible links.

        The editor authoritatively owns link state today (Flow.connect is
        not yet wired to the UI), so we walk slot 0 of the editor to
        recover them.
        """
        result: list[dict] = []
        for link_tag in dpg.get_item_children(self._node_editor_tag, 0) or []:
            try:
                conf = dpg.get_item_configuration(link_tag)
            except SystemError:
                logger.debug("Skipped link %s during save", link_tag, exc_info=True)
                continue
            endpoint_a = self._attr_to_port.get(conf.get("attr_1"))
            endpoint_b = self._attr_to_port.get(conf.get("attr_2"))
            if endpoint_a is None or endpoint_b is None:
                continue
            # Normalise to (output, input) order. DPG doesn't guarantee
            # which of attr_1 / attr_2 is the source.
            if endpoint_a[1] == "output" and endpoint_b[1] == "input":
                src, dst = endpoint_a, endpoint_b
            elif endpoint_a[1] == "input" and endpoint_b[1] == "output":
                src, dst = endpoint_b, endpoint_a
            else:
                logger.debug("Skipping link with same-kind endpoints: %s", link_tag)
                continue
            result.append({
                "src_node":   node_ids[id(src[0])],
                "src_output": src[2],
                "dst_node":   node_ids[id(dst[0])],
                "dst_input":  dst[2],
            })
        return result

    # ── Button / menu callbacks ────────────────────────────────────────────────

    def _on_exit_clicked(self, sender: DpgTag | None = None) -> None:
        logger.info("Exiting node editor")
        self._clear_nodes()
        self._page_manager.activate(self._page_manager.start_page)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _jsonable(value: object) -> object:
    """Coerce ``value`` to a JSON-serialisable form (recursive for containers)."""
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    return value
