import sys
import argparse

from PyQt6.QtWidgets import QApplication

from constants import APP_NAME, APP_WIDTH, APP_HEIGHT
from ui.main_window import MainWindow


class App:
    def __init__(self, width: int, height: int) -> None:
        self._qt_app = QApplication(sys.argv)
        self._main_window = MainWindow(width, height)

    def run(self) -> None:
        self._main_window.show()
        sys.exit(self._qt_app.exec())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Image Inquest Application")
    parser.add_argument("--width", type=int, default=APP_WIDTH, help="Width of the application window")
    parser.add_argument("--height", type=int, default=APP_HEIGHT, help="Height of the application window")
    args = parser.parse_args()
    App(args.width, args.height).run()
