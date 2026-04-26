from __future__ import annotations

from enum import IntEnum

from typing_extensions import override

from core import notifications
from core.io_data import IMAGE_TYPES
from core.node_base import NodeBase, NodeParam, NodeParamType
from core.port import InputPort, OutputPort


class NotifySeverity(IntEnum):
    """Severity choice for the :class:`Notify` debug node."""
    #: Emit a warning via :mod:`core.notifications`. Run continues; the
    #: warning surfaces in the floating banner (yellow).
    WARNING = 0
    #: Raise a ``RuntimeError`` carrying the configured message. Run
    #: aborts; the banner shows the standard red error.
    ERROR = 1


class Notify(NodeBase):
    """Debug node that emits a notification (warning or error) per frame.

    Use it to exercise the warning- and error-banner UI without
    contriving real failures — drop it inline in a flow, pick a
    severity, type a message, hit Run.

    The image input is forwarded unchanged on the output so the node
    can sit between any two image nodes without altering the pipeline.
    For ``WARNING`` the run keeps going (warnings are non-blocking by
    contract); for ``ERROR`` the node raises and the run aborts at
    this node, the same way :class:`ThrowException` does.

    Parameters:
      severity -- :class:`NotifySeverity` choice; warning vs. error.
      message  -- Free-form text shown in the banner / exception.
    """

    def __init__(self) -> None:
        super().__init__("Notify", section="Debug")
        self._severity: NotifySeverity = NotifySeverity.WARNING
        self._message:  str = "Notify debug node fired"

        self._add_input(InputPort("image", set(IMAGE_TYPES)))
        self._add_param(NodeParam(
            "severity",
            NodeParamType.ENUM,
            default=NotifySeverity.WARNING,
            metadata={"enum": NotifySeverity},
        ))
        self._add_param(NodeParam(
            "message",
            NodeParamType.STRING,
            default="Notify debug node fired",
            metadata={"placeholder": "message shown in the banner"},
        ))
        self._add_output(OutputPort("image", set(IMAGE_TYPES)))

        self._apply_default_params()

    # ── Properties ─────────────────────────────────────────────────────────────

    @property
    def severity(self) -> NotifySeverity:
        return self._severity

    @severity.setter
    def severity(self, value: int | NotifySeverity) -> None:
        try:
            self._severity = NotifySeverity(value)
        except ValueError as exc:
            raise ValueError(
                f"severity must be one of {[s.value for s in NotifySeverity]} "
                f"(got {value!r})"
            ) from exc

    @property
    def message(self) -> str:
        return self._message

    @message.setter
    def message(self, value: str) -> None:
        self._message = str(value)

    # ── NodeBase interface ─────────────────────────────────────────────────────

    @override
    def process_impl(self) -> None:
        in_data = self.inputs[0].data
        if self._severity is NotifySeverity.ERROR:
            raise RuntimeError(self._message)
        notifications.warn(self._message)
        self.outputs[0].send(in_data)
