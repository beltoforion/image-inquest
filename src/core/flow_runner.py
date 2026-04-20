from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal, Slot

from core.flow import Flow

logger = logging.getLogger(__name__)


class FlowRunner(QObject):
    """Runs :meth:`Flow.run` on whichever thread the ``QObject`` lives on.

    Intended to be moved onto a :class:`QThread` so expensive
    ``process_impl`` calls do not stall the Qt event loop. The runner
    holds no UI state; it only exposes two queued signals the caller can
    connect to slots on the main thread:

      - :attr:`finished` — emitted once the source nodes have fully
        drained and the graph settled without error.
      - :attr:`failed`   — emitted with a human-readable detail string
        if any node raised. Exceptions are caught here (rather than
        letting them propagate across the thread boundary, which Qt
        cannot marshal) so the UI can show a banner instead of
        crashing the worker.
    """

    finished = Signal()
    failed = Signal(str)

    def __init__(self, flow: Flow, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._flow = flow

    @Slot()
    def run(self) -> None:
        try:
            self._flow.run()
        except Exception as err:
            logger.exception("Flow run failed")
            detail = str(err).strip() or "(no message)"
            self.failed.emit(f"{type(err).__name__}: {detail}")
            return
        self.finished.emit()
