from __future__ import annotations

from abc import ABCMeta

from PySide6.QtWidgets import QWidget


class _WidgetMeta(type(QWidget), ABCMeta):
    """Combined metaclass for abstract QWidget subclasses.

    PySide6 uses Shiboken's ObjectType as the metaclass for all QWidget
    subclasses, while ABCMeta is a separate Python metaclass.  Inheriting
    from both without this bridge raises a TypeError at class-definition
    time.  Declare any abstract widget like::

        class MyWidget(QWidget, metaclass=_WidgetMeta):
            @abstractmethod
            def some_method(self) -> None: ...
    """
