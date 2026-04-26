"""Process-wide hub for non-fatal notifications.

Nodes (and other Qt-free producers) emit warnings or errors via
:func:`warn` / :func:`error`; the UI subscribes once at startup and
surfaces each one in the floating banner. The hub itself is Qt-free
so node code can call into it without dragging PySide6 into modules
that are meant to run headlessly.

Subscribers receive notifications synchronously on whichever thread
emits them — the per-frame node loop typically runs on a worker
thread. Subscribers that need UI-thread dispatch (e.g. the banner)
must marshal across themselves, normally by emitting a queued Qt
signal from inside the callback.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from enum import Enum

logger = logging.getLogger(__name__)


class Severity(Enum):
    """Severity tag carried with every emitted notification."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


Subscriber = Callable[[Severity, str], None]

#: Active subscribers. Iterated over a snapshot during dispatch so a
#: callback that subscribes / unsubscribes mid-emit doesn't disturb
#: the in-flight loop.
_subscribers: list[Subscriber] = []


def subscribe(callback: Subscriber) -> None:
    """Register *callback* to receive every emitted notification.

    Idempotent — re-subscribing the same callback is a no-op so a
    UI page that re-attaches on flow reload doesn't accumulate
    duplicate handlers.
    """
    if callback not in _subscribers:
        _subscribers.append(callback)


def unsubscribe(callback: Subscriber) -> None:
    """Remove *callback*; no-op if it was never subscribed."""
    try:
        _subscribers.remove(callback)
    except ValueError:
        pass


def info(message: str) -> None:
    """Emit an informational message — neutral, no problem implied.

    Use for status updates the user might want to see surfaced in
    the UI (e.g. a long-running operation announcing a milestone, a
    node reporting what it's doing). The run keeps going.
    """
    _emit(Severity.INFO, message)


def warn(message: str) -> None:
    """Emit a warning — non-fatal, the run keeps going.

    Use for issues the user should see but that don't justify
    aborting the flow (e.g. a single frame failing to render in the
    preview, a sink swallowing a malformed payload, …).
    """
    _emit(Severity.WARNING, message)


def error(message: str) -> None:
    """Emit an error — for fatal-but-recoverable issues that the
    user must see.

    Does **not** raise; callers that need the run to abort should
    raise an exception in addition to (or instead of) calling this.
    Useful when the failure has already been handled and the run
    can continue, but the user should still be told about it.
    """
    _emit(Severity.ERROR, message)


def _emit(severity: Severity, message: str) -> None:
    for cb in list(_subscribers):
        try:
            cb(severity, message)
        except Exception:
            # A buggy subscriber must not break the producer or
            # silence other subscribers. Log and continue.
            logger.exception(
                "notifications subscriber %r raised; continuing dispatch", cb,
            )
