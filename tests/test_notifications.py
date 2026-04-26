"""Tests for the process-wide notifications hub.

Covers subscribe / unsubscribe semantics, severity dispatch, and the
guarantees the Display preview path relies on (subscribers don't break
producers, no-op unsubscribe is safe, idempotent subscribe).
"""

from __future__ import annotations

import pytest

from core import notifications


@pytest.fixture(autouse=True)
def _isolated_subscribers():
    """Each test starts with an empty subscriber list and restores it.

    The hub uses module-level state, so test order would otherwise
    leak subscriptions across cases.
    """
    saved = list(notifications._subscribers)
    notifications._subscribers.clear()
    yield
    notifications._subscribers.clear()
    notifications._subscribers.extend(saved)


def test_warn_dispatches_to_subscriber():
    seen: list[tuple[notifications.Severity, str]] = []
    notifications.subscribe(lambda sev, msg: seen.append((sev, msg)))
    notifications.warn("hello")
    assert seen == [(notifications.Severity.WARNING, "hello")]


def test_error_dispatches_with_error_severity():
    seen: list[tuple[notifications.Severity, str]] = []
    notifications.subscribe(lambda sev, msg: seen.append((sev, msg)))
    notifications.error("boom")
    assert seen == [(notifications.Severity.ERROR, "boom")]


def test_error_does_not_raise():
    """``notifications.error`` is for surfacing — callers raise explicitly."""
    notifications.error("just a notification, not an exception")  # no raise


def test_subscribe_is_idempotent():
    cb_calls: list[int] = []

    def cb(sev, msg):
        cb_calls.append(1)

    notifications.subscribe(cb)
    notifications.subscribe(cb)  # second subscribe must be a no-op
    notifications.warn("once")
    assert cb_calls == [1]


def test_unsubscribe_removes_callback():
    seen: list[str] = []

    def cb(sev, msg):
        seen.append(msg)

    notifications.subscribe(cb)
    notifications.unsubscribe(cb)
    notifications.warn("nope")
    assert seen == []


def test_unsubscribe_unknown_is_silent():
    """Pages may unsubscribe at teardown without tracking whether they ever
    subscribed; the no-op contract keeps that simple."""
    notifications.unsubscribe(lambda sev, msg: None)  # not subscribed


def test_subscriber_exception_does_not_break_producer_or_other_subscribers():
    seen: list[str] = []

    def bad(sev, msg):
        raise RuntimeError("subscriber bug")

    def good(sev, msg):
        seen.append(msg)

    notifications.subscribe(bad)
    notifications.subscribe(good)
    notifications.warn("x")  # producer must not see the exception
    assert seen == ["x"]


def test_dispatch_iterates_over_snapshot():
    """A subscriber that unsubscribes itself mid-emit must not perturb
    the live iteration order."""
    seen: list[str] = []

    def first(sev, msg):
        notifications.unsubscribe(first)
        seen.append("first")

    def second(sev, msg):
        seen.append("second")

    notifications.subscribe(first)
    notifications.subscribe(second)
    notifications.warn("once")
    # Both still ran on this dispatch despite ``first`` removing itself.
    assert seen == ["first", "second"]
    # And ``first`` is gone for the next dispatch.
    seen.clear()
    notifications.warn("twice")
    assert seen == ["second"]
