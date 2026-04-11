from dataclasses import dataclass, field


@dataclass
class NodeAttribute:
    """An input or output port on a node."""
    name: str


@dataclass
class Node:
    """A single node in a flow."""
    id: int
    label: str
    inputs: list[NodeAttribute] = field(default_factory=list)
    outputs: list[NodeAttribute] = field(default_factory=list)


@dataclass
class Link:
    """A connection from an output attribute on one node to an input
    attribute on another."""
    source_node_id: int
    source_attr: str
    target_node_id: int
    target_attr: str


class Flow:
    """A node-based processing flow.

    Pure domain model: a named collection of nodes and the links between
    them. Framework-agnostic - contains no DearPyGUI (or any other UI)
    dependencies. The node editor page is responsible for keeping its
    visual widgets in sync with an instance of this class.
    """

    def __init__(self, name: str = "Untitled") -> None:
        self._name: str = name
        self._nodes: dict[int, Node] = {}
        self._links: list[Link] = []
        self._next_node_id: int = 1

    @property
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, value: str) -> None:
        self._name = value

    @property
    def nodes(self) -> list[Node]:
        return list(self._nodes.values())

    @property
    def links(self) -> list[Link]:
        return list(self._links)

    def get_node(self, node_id: int) -> Node | None:
        return self._nodes.get(node_id)

    def add_node(
        self,
        label: str,
        inputs: list[str] | None = None,
        outputs: list[str] | None = None,
    ) -> Node:
        node_id = self._next_node_id
        self._next_node_id += 1
        node = Node(
            id=node_id,
            label=label,
            inputs=[NodeAttribute(name=n) for n in (inputs or [])],
            outputs=[NodeAttribute(name=n) for n in (outputs or [])],
        )
        self._nodes[node_id] = node
        return node

    def remove_node(self, node_id: int) -> None:
        if node_id not in self._nodes:
            return
        del self._nodes[node_id]
        self._links = [
            link for link in self._links
            if link.source_node_id != node_id and link.target_node_id != node_id
        ]

    def add_link(
        self,
        source_node_id: int,
        source_attr: str,
        target_node_id: int,
        target_attr: str,
    ) -> Link:
        link = Link(
            source_node_id=source_node_id,
            source_attr=source_attr,
            target_node_id=target_node_id,
            target_attr=target_attr,
        )
        self._links.append(link)
        return link

    def remove_link(self, link: Link) -> None:
        if link in self._links:
            self._links.remove(link)

    def clear(self) -> None:
        self._nodes.clear()
        self._links.clear()
        self._next_node_id = 1
