from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, QTimer, Qt
from PySide6.QtGui import QColor, QConicalGradient, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ui.theme import STATUS_MUTED_COLOR


class SpinnerWidget(QWidget):
    """Small indeterminate spinner suitable for status bars and toolbars.

    Renders a rotating conical-gradient arc at a fixed size. The widget
    is always visible (so containers like :class:`QToolBar` reserve
    space for it from first layout), but draws nothing while idle — so
    a stopped spinner is indistinguishable from empty space. Calling
    :meth:`start` begins animating; :meth:`stop` freezes and blanks the
    widget again.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        size: int = 14,
        interval_ms: int = 60,
        color: QColor | None = None,
    ) -> None:
        super().__init__(parent)
        self._size = size
        self._angle = 0
        self._spinning = False
        # Status-bar spinner defaults to the muted status colour so it
        # sits quietly alongside the "Running…" label without shouting.
        self._color = QColor(color if color is not None else STATUS_MUTED_COLOR)

        self.setFixedSize(QSize(size, size))
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._advance)

    # ── Public API ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        self._spinning = True
        self._timer.start()
        self.update()

    def stop(self) -> None:
        self._timer.stop()
        self._spinning = False
        self.update()

    # ── Qt overrides ───────────────────────────────────────────────────────────

    def paintEvent(self, _event) -> None:  # type: ignore[override]
        if not self._spinning:
            # Idle: paint nothing so the widget reads as empty space
            # even though its fixed size still reserves a layout slot.
            return

        # Scale the pen with the overall size so the arc stays visually
        # balanced at both the 14 px status-bar size and the 36 px
        # toolbar size. The inset keeps the stroke fully inside the
        # widget rect so anti-aliasing doesn't clip against the
        # background.
        pen_width = max(2, self._size // 7)
        inset = pen_width / 2 + 0.5
        rect = QRectF(inset, inset, self._size - 2 * inset, self._size - 2 * inset)

        # A conical gradient from transparent → solid produces the
        # comet-tail fade that readers expect from a spinner; rotating
        # the gradient start each tick animates it.
        grad = QConicalGradient(rect.center(), -self._angle)
        transparent = QColor(self._color)
        transparent.setAlpha(0)
        grad.setColorAt(0.0, self._color)
        grad.setColorAt(1.0, transparent)

        pen = QPen(grad, pen_width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(pen)
        painter.drawArc(rect, 0, 360 * 16)
        painter.end()

    def _advance(self) -> None:
        self._angle = (self._angle + 30) % 360
        self.update()
