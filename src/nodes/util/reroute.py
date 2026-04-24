from __future__ import annotations

from typing_extensions import override

from core.io_data import IMAGE_TYPES
from core.node_base import NodeBase, NodeParam
from core.port import InputPort, OutputPort


class Reroute(NodeBase):
    """Zero-logic pass-through used to route links around other nodes.

    A ``Reroute`` has one input and one output, both accepting the same
    image types the rest of the pipeline does. It does no processing:
    every frame that arrives on the input is forwarded verbatim to the
    output. The value of a reroute is purely visual — it lets the user
    pin a knick-point on an otherwise straight link so the graph can
    meander around densely packed nodes.

    Reroutes are created implicitly by the editor (double-click on a
    link → insert reroute at the cursor) and never appear in the node
    palette, so the section name is intentionally sentinel-valued to
    keep them out of ``NodeList`` listings.
    """

    #: Sentinel section name. ``NodeList`` filters against this literal
    #: so reroutes never show up in the palette — they can only be
    #: instantiated by the editor itself. Must be a string literal in
    #: the super().__init__() call because :class:`NodeRegistry` scans
    #: the section via AST and only recognises literals.
    HIDDEN_SECTION: str = "__hidden__"

    def __init__(self) -> None:
        super().__init__("Reroute", section="__hidden__")
        self._add_input(InputPort("in", set(IMAGE_TYPES)))
        self._add_output(OutputPort("out", set(IMAGE_TYPES)))

    @property
    @override
    def params(self) -> list[NodeParam]:
        return []

    @override
    def process_impl(self) -> None:
        self.outputs[0].send(self.inputs[0].data)
