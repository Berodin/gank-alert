"""Dev-only helper: render the main window off-screen and save a PNG,
so the design can be inspected without popping up a real window."""

import sys

from PySide6.QtWidgets import QApplication

from gank_client import theme
from gank_client.main_window import MainWindow

app = QApplication(sys.argv)
theme.load_fonts()
app.setStyleSheet(theme.STYLESHEET)

window = MainWindow()
window.resize(900, 640)
window.show()
app.processEvents()

pixmap = window.grab()
out_path = sys.argv[1] if len(sys.argv) > 1 else "screenshot.png"
pixmap.save(out_path)
print(f"saved {out_path}")
