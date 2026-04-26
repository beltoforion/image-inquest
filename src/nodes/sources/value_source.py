from __future__ import annotations

from collections.abc import Iterator

from typing_extensions import override

from core.io_data import IoData, IoDataType
from core.node_base import NodeParam, NodeParamType, SourceNodeBase
from core.port import OutputPort


class ValueSource(SourceNodeBase):
    """Source node that emits a SCALAR counter, one value per frame.

    Drives downstream nodes with a numeric stream — animate a
    Math expression's ``a``, an Overlay's rotation angle, etc.

    Parameters:
      min_value  -- first emitted value (inclusive).
      max_value  -- inclusive upper bound; the iterator stops once
                    ``min_value + n * increment`` would exceed it.
      increment  -- step size between emitted values (must be > 0).
                    Whole-number increments emit ints (so a
                    downstream Display shows ``42`` rather than
                    ``42.0``); fractional increments promote every
                    emitted value to float.
      loop       -- when False (default), emits the range once and
                    finishes; when True, repeats it
                    :data:`_LOOP_CYCLES` times so a wraparound is
                    observable in a finite run.

    The looping cycle count is bounded because emitting forever would
    only stop on a Stop click — the cap keeps a forgotten ``loop=True``
    from filling logs / output files indefinitely.
    """

    #: How many times the counter cycles when ``loop=True``. Bounded
    #: so a stray ``loop=True`` doesn't run indefinitely if the user
    #: walks away.
    _LOOP_CYCLES: int = 10

    def __init__(self) -> None:
        super().__init__("Value Source", section="Sources")
        self._min_value: int = 0
        self._max_value: int = 99
        self._increment: float = 1.0
        self._loop: bool = False
        self._add_param(NodeParam(
            "min_value",
            NodeParamType.INT,
            default=0,
        ))
        self._add_param(NodeParam(
            "max_value",
            NodeParamType.INT,
            default=99,
        ))
        self._add_param(NodeParam(
            "increment",
            NodeParamType.FLOAT,
            default=1.0,
        ))
        self._add_param(NodeParam(
            "loop",
            NodeParamType.BOOL,
            default=False,
        ))
        self._add_output(OutputPort("value", {IoDataType.SCALAR}))
        self._apply_default_params()

    # ── Properties ─────────────────────────────────────────────────────────────

    @property
    def min_value(self) -> int:
        return self._min_value

    @min_value.setter
    def min_value(self, value: int) -> None:
        self._min_value = int(value)

    @property
    def max_value(self) -> int:
        return self._max_value

    @max_value.setter
    def max_value(self, value: int) -> None:
        self._max_value = int(value)

    @property
    def increment(self) -> float:
        return self._increment

    @increment.setter
    def increment(self, value: float) -> None:
        v = float(value)
        if v <= 0.0:
            raise ValueError(f"increment must be > 0 (got {v})")
        self._increment = v

    @property
    def loop(self) -> bool:
        return self._loop

    @loop.setter
    def loop(self, value: bool) -> None:
        self._loop = bool(value)

    # ── SourceNodeBase interface ────────────────────────────────────────────────

    @override
    def iter_frames(self) -> Iterator[None]:
        """Per-frame generator: one ``yield`` per emitted scalar.

        Letting :class:`core.flow.Flow.run` round-robin streaming
        sources requires this — without per-frame yielding two
        ``ValueSource``s feeding two param ports on the same node
        produce only one composite frame total (the first source
        drains entirely before the second sends anything; see
        :meth:`SourceNodeBase.iter_frames`).
        """
        # Defensive — both can only happen if a setter was bypassed
        # (the increment setter rejects 0 / negatives, and an empty
        # range just emits nothing rather than raising).
        if self._increment <= 0.0:
            return
        if self._max_value < self._min_value:
            return

        cycles = self._LOOP_CYCLES if self._loop else 1
        # Whole-number increment + integer bounds → emit ints, so a
        # downstream Display shows ``42`` rather than ``42.0``. Any
        # fractional increment promotes every emitted value to float.
        emit_int = self._increment.is_integer()
        # Tolerance on the upper bound so float drift (e.g. 10 *
        # 0.1 == 1.0000000000000002) doesn't truncate the last value.
        tol = abs(self._increment) * 1e-9
        for _ in range(cycles):
            n = 0
            while True:
                value: int | float = self._min_value + n * self._increment
                if value > self._max_value + tol:
                    break
                if emit_int:
                    value = int(value)
                self.outputs[0].send(IoData.from_scalar(value))
                n += 1
                yield

    @override
    def process_impl(self) -> None:
        """Direct-invocation path used by tests: drain :meth:`iter_frames`
        in one call, mirroring the pre-round-robin all-at-once semantics."""
        for _ in self.iter_frames():
            pass
