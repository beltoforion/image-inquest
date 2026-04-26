from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal, Slot

from core.flow import Flow
from core.node_base import NodeBase, set_process_observer

logger = logging.getLogger(__name__)


class FlowRunner(QObject):
    """Runs :meth:`Flow.run` on whichever thread the ``QObject`` lives on.

    Intended to be moved onto a :class:`QThread` so expensive
    ``process_impl`` calls do not stall the Qt event loop. The runner
    holds no UI state; it only exposes queued signals the caller can
    connect to slots on the main thread:

      - :attr:`finished` — emitted once the source nodes have fully
        drained and the graph settled without error.
      - :attr:`failed`   — emitted with a human-readable detail string
        if any node raised. Exceptions are caught here (rather than
        letting them propagate across the thread boundary, which Qt
        cannot marshal) so the UI can show a banner instead of
        crashing the worker.
      - :attr:`node_started` — emitted with the node's display name
        just before each :meth:`NodeBase.process_impl` call. The UI
        uses this to show which node is currently running.
    """

    finished = Signal()
    failed = Signal(str)
    node_started = Signal(str)

    def __init__(self, flow: Flow, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._flow = flow

    @Slot()
    def request_stop(self) -> None:
        """Forward a Stop click from the UI thread to the running flow.

        Sets a polled flag inside :class:`Flow.run` — the worker thread
        keeps decoding the in-flight frame, then unwinds and fires
        ``after_run`` on every node so file handles / video captures
        release. No thread synchronisation needed beyond what the GIL
        already gives us for the bool write.
        """
        self._flow.request_stop()

    @Slot()
    def run(self) -> None:
        # Route every node's process() call through our node_started
        # signal. The observer fires on the worker thread, but the
        # signal carries across via a queued connection so the UI slot
        # sees it on the main thread. The install/clear pair is a
        # try/finally so we don't leak the hook when a run raises.
        set_process_observer(self._on_node_processing)
        try:
            self._flow.run()
        except Exception as err:
            logger.exception("Flow run failed")
            detail = str(err).strip() or "(no message)"
            self.failed.emit(f"{type(err).__name__}: {detail}")
            return
        finally:
            set_process_observer(None)
        self.finished.emit()

    def _on_node_processing(self, node: NodeBase) -> None:
        self.node_started.emit(node.display_name)
