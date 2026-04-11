from ui.page import Page


class PageManager:
    """Owns a set of named pages and guarantees that only one is active."""

    def __init__(self) -> None:
        self._pages: dict[str, Page] = {}
        self._active: Page | None = None

    def register(self, page: Page) -> None:
        if page.name in self._pages:
            raise ValueError(f"Page '{page.name}' is already registered")
        self._pages[page.name] = page

    def activate(self, page: Page) -> None:
        if page.name not in self._pages:
            raise KeyError(f"Page '{page.name}' is not registered")

        if self._active is page:
            return

        if self._active is not None:
            self._active.deactivate()

        page.activate()
        self._active = page
