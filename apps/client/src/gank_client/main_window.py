from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from gank_client import theme
from gank_client.widgets import GankFeedRow, HudPanel, SectionTitle, fix_transparency

# Placeholder feed data -- apps/api isn't wired up yet, this is here to
# validate the visual design end to end.
MOCK_FEED = [
    dict(time_label="00:44", system_name="Uedama", victim_ship="Iteron Mark V",
         ganker_tag="CODE.", jumps=2, threat="fresh"),
    dict(time_label="00:31", system_name="Sivala", victim_ship="Retriever",
         ganker_tag="CODE.", jumps=5, threat="recent"),
    dict(time_label="23:58", system_name="Perimeter", victim_ship="Bestower",
         ganker_tag="Snuffed Out", jumps=7, threat="recent"),
    dict(time_label="23:40", system_name="Niarja", victim_ship="Providence",
         ganker_tag="CODE.", jumps=11, threat="stale"),
]


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("GANK ALERT")
        self.resize(880, 640)
        self.setMinimumSize(720, 520)

        central = QWidget()
        central.setStyleSheet(f"background-color: {theme.BG_VOID};")
        self.setCentralWidget(central)

        outer = QVBoxLayout(central)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(16)

        outer.addLayout(self._build_header())

        body = QHBoxLayout()
        body.setSpacing(16)
        body.addWidget(self._build_status_panel(), stretch=0)
        body.addWidget(self._build_feed_panel(), stretch=1)
        outer.addLayout(body, stretch=1)

        fix_transparency(central)

    def _build_header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(2)

        wordmark = QLabel("GANK ALERT")
        wordmark.setObjectName("wordmark")
        sub = QLabel("REGION WATCH — THE FORGE")
        sub.setObjectName("wordmarkSub")

        title_col.addWidget(wordmark)
        title_col.addWidget(sub)
        row.addLayout(title_col)
        row.addStretch()

        status_dot = QLabel("● LIVE")
        status_dot.setStyleSheet(
            f"color: {theme.ACCENT_GREEN}; font-family: '{theme.FONT_MONO}'; "
            f"font-size: 12px; letter-spacing: 2px;"
        )
        row.addWidget(status_dot, alignment=Qt.AlignmentFlag.AlignVCenter)
        return row

    def _build_status_panel(self) -> HudPanel:
        panel = HudPanel()
        panel.setFixedWidth(260)
        layout = QVBoxLayout(panel)
        layout.setSpacing(14)

        layout.addWidget(SectionTitle("PILOT"))

        name_lbl = QLabel("NOT LOGGED IN")
        name_lbl.setStyleSheet(
            f"font-family: '{theme.FONT_DISPLAY}'; font-size: 15px; color: {theme.TEXT_DIM};"
        )
        layout.addWidget(name_lbl)

        login_btn = QPushButton("LOG IN WITH EVE")
        layout.addWidget(login_btn)

        layout.addSpacing(10)
        layout.addWidget(SectionTitle("CURRENT SYSTEM"))
        system_lbl = QLabel("—")
        system_lbl.setStyleSheet(
            f"font-family: '{theme.FONT_DISPLAY}'; font-size: 15px; color: {theme.TEXT_PRIMARY};"
        )
        layout.addWidget(system_lbl)

        layout.addSpacing(10)
        layout.addWidget(SectionTitle("NEAREST GANK"))

        dist_row = QHBoxLayout()
        dist_val = QLabel("2")
        dist_val.setProperty("role", "statValue")
        dist_unit = QLabel("JUMPS")
        dist_unit.setProperty("role", "statUnit")
        dist_row.addWidget(dist_val)
        dist_row.addWidget(dist_unit, alignment=Qt.AlignmentFlag.AlignBottom)
        dist_row.addStretch()
        layout.addLayout(dist_row)

        last_seen = QLabel("Uedama · CODE. · 12m ago")
        last_seen.setProperty("role", "dim")
        layout.addWidget(last_seen)

        layout.addStretch()
        return panel

    def _build_feed_panel(self) -> HudPanel:
        panel = HudPanel()
        layout = QVBoxLayout(panel)
        layout.setSpacing(10)

        layout.addWidget(SectionTitle("REGION FEED"))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent;")

        feed_widget = QWidget()
        feed_widget.setStyleSheet("background: transparent;")
        feed_layout = QVBoxLayout(feed_widget)
        feed_layout.setSpacing(4)

        for entry in MOCK_FEED:
            feed_layout.addWidget(GankFeedRow(**entry))
        feed_layout.addStretch()

        scroll.setWidget(feed_widget)
        layout.addWidget(scroll, stretch=1)
        return panel
