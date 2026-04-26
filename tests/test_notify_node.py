"""Tests for the ``Notify`` debug node.

Covers the two severities: ``WARNING`` emits via the notifications
hub and forwards the input on the output port; ``ERROR`` raises a
``RuntimeError`` carrying the configured message and does not emit
on the hub (the run aborts at this node).
"""

from __future__ import annotations

import numpy as np
import pytest

from core import notifications
from core.io_data import IoData
from nodes.filters.notify import Notify, NotifySeverity


@pytest.fixture(autouse=True)
def _isolated_subscribers():
    saved = list(notifications._subscribers)
    notifications._subscribers.clear()
    yield
    notifications._subscribers.clear()
    notifications._subscribers.extend(saved)


def _frame() -> IoData:
    return IoData.from_image(np.zeros((4, 4, 3), dtype=np.uint8))


def test_warning_severity_emits_and_forwards_input():
    seen: list[tuple[notifications.Severity, str]] = []
    notifications.subscribe(lambda sev, msg: seen.append((sev, msg)))

    n = Notify()
    n.message = "heads up"
    forwarded: list[IoData] = []
    n.outputs[0].connect(_capture_into(forwarded))

    n.inputs[0].receive(_frame())

    assert seen == [(notifications.Severity.WARNING, "heads up")]
    assert len(forwarded) == 1


def test_error_severity_raises_with_message():
    seen: list[tuple[notifications.Severity, str]] = []
    notifications.subscribe(lambda sev, msg: seen.append((sev, msg)))

    n = Notify()
    n.severity = NotifySeverity.ERROR
    n.message = "kaboom"

    with pytest.raises(RuntimeError, match="kaboom"):
        n.inputs[0].receive(_frame())

    # Errors abort the run via the exception path; the hub is not used.
    assert seen == []


def test_severity_setter_rejects_invalid_value():
    n = Notify()
    with pytest.raises(ValueError):
        n.severity = 99


def test_default_severity_is_warning():
    n = Notify()
    assert n.severity is NotifySeverity.WARNING


# ── helpers ────────────────────────────────────────────────────────────────────

def _capture_into(bucket: list[IoData]):
    """Build a sink-style InputPort that appends every received IoData."""
    from core.io_data import IMAGE_TYPES
    from core.port import InputPort

    port = InputPort("sink", set(IMAGE_TYPES))
    port.set_on_state_changed(lambda: bucket.append(port.data))
    return port
