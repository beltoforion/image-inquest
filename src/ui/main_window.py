from PyQt6.QtWidgets import QMainWindow, QStackedWidget

from constants import APP_NAME
from ui.node_editor_page import NodeEditorPage
from ui.page_manager import PageManager
from ui.start_page import StartPage


class MainWindow(QMainWindow):
    def __init__(self, width: int, height: int) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(width, height)

        file_menu = self.menuBar().addMenu("File")
        file_menu.addAction("New", self._on_new)
        file_menu.addAction("Save As", self._on_save)

        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)

        self._pages = PageManager(self._stack, self.menuBar())
        self._pages.register(StartPage(self.menuBar(), self._pages))
        self._pages.register(NodeEditorPage(self.menuBar(), self._pages))
        self._pages.activate(self._pages.start_page)

    def _on_new(self) -> None:
        print("New")

    def _on_save(self) -> None:
        print("Save As")
