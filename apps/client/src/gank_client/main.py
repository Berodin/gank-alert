from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from gank_client import theme
from gank_client.main_window import MainWindow


def run() -> None:
    app = QApplication(sys.argv)
    theme.load_fonts()
    app.setStyleSheet(theme.STYLESHEET)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    run()
