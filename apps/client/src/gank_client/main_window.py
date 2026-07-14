from __future__ import annotations

import logging
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from gank_shared.esi import ESIClient

from gank_client import theme
from gank_client.controller import Controller
from gank_client.widgets import GankFeedRow, HudPanel, SectionTitle, fix_transparency

logger = logging.getLogger("gank_client.main_window")


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("GANK ALERT")
        self.resize(880, 640)
        self.setMinimumSize(720, 520)

        self.esi = ESIClient(component="client")
        self.controller = Controller()

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

        self.controller.login_changed.connect(self._on_login_changed)
        self.controller.region_changed.connect(self._on_region_changed)
        self.controller.feed_updated.connect(self._on_feed_updated)
        self.controller.location_updated.connect(self._on_location_updated)

        self._latest_feed: list[dict] = []
        self._my_location: dict | None = None
        self._on_login_changed()
        self._on_region_changed()
        self.controller.start()

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self.esi.close()
        super().closeEvent(event)

    def _build_header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(2)

        wordmark = QLabel("GANK ALERT")
        wordmark.setObjectName("wordmark")
        self.region_sub_lbl = QLabel()
        self.region_sub_lbl.setObjectName("wordmarkSub")

        title_col.addWidget(wordmark)
        title_col.addWidget(self.region_sub_lbl)
        row.addLayout(title_col)
        row.addStretch()

        region_btn = QPushButton("CHANGE REGION")
        region_btn.clicked.connect(self._on_change_region)
        row.addWidget(region_btn, alignment=Qt.AlignmentFlag.AlignVCenter)

        status_dot = QLabel("● LIVE")
        status_dot.setStyleSheet(
            f"color: {theme.ACCENT_GREEN}; font-family: '{theme.FONT_MONO}'; "
            f"font-size: 12px; letter-spacing: 2px; margin-left: 12px;"
        )
        row.addWidget(status_dot, alignment=Qt.AlignmentFlag.AlignVCenter)
        return row

    def _build_status_panel(self) -> HudPanel:
        panel = HudPanel()
        panel.setFixedWidth(260)
        layout = QVBoxLayout(panel)
        layout.setSpacing(14)

        layout.addWidget(SectionTitle("PILOT"))

        self.name_lbl = QLabel("NOT LOGGED IN")
        self.name_lbl.setStyleSheet(
            f"font-family: '{theme.FONT_DISPLAY}'; font-size: 15px; color: {theme.TEXT_DIM};"
        )
        layout.addWidget(self.name_lbl)

        self.login_btn = QPushButton("LOG IN WITH EVE")
        self.login_btn.clicked.connect(self._on_login_button)
        layout.addWidget(self.login_btn)

        layout.addSpacing(10)
        layout.addWidget(SectionTitle("CURRENT SYSTEM"))
        self.system_lbl = QLabel("—")
        self.system_lbl.setStyleSheet(
            f"font-family: '{theme.FONT_DISPLAY}'; font-size: 15px; color: {theme.TEXT_PRIMARY};"
        )
        layout.addWidget(self.system_lbl)

        layout.addSpacing(10)
        layout.addWidget(SectionTitle("NEAREST GANK"))

        dist_row = QHBoxLayout()
        self.dist_val = QLabel("—")
        self.dist_val.setProperty("role", "statValue")
        dist_unit = QLabel("JUMPS")
        dist_unit.setProperty("role", "statUnit")
        dist_row.addWidget(self.dist_val)
        dist_row.addWidget(dist_unit, alignment=Qt.AlignmentFlag.AlignBottom)
        dist_row.addStretch()
        layout.addLayout(dist_row)

        self.last_seen_lbl = QLabel("no data yet")
        self.last_seen_lbl.setProperty("role", "dim")
        layout.addWidget(self.last_seen_lbl)

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

        self.feed_widget = QWidget()
        self.feed_widget.setStyleSheet("background: transparent;")
        self.feed_layout = QVBoxLayout(self.feed_widget)
        self.feed_layout.setSpacing(4)
        self.feed_layout.addStretch()

        scroll.setWidget(self.feed_widget)
        layout.addWidget(scroll, stretch=1)
        return panel

    def _on_login_button(self) -> None:
        if self.controller.api.is_logged_in:
            self.controller.logout()
        else:
            self.login_btn.setText("WAITING FOR BROWSER…")
            self.login_btn.setEnabled(False)
            self.controller.begin_login()

    def _on_login_changed(self) -> None:
        api = self.controller.api
        self.login_btn.setEnabled(True)
        if api.is_logged_in:
            self.name_lbl.setText(api.character_name.upper())
            self.name_lbl.setStyleSheet(
                f"font-family: '{theme.FONT_DISPLAY}'; font-size: 15px; color: {theme.ACCENT_CYAN};"
            )
            self.login_btn.setText("LOG OUT")
        else:
            self.name_lbl.setText("NOT LOGGED IN")
            self.name_lbl.setStyleSheet(
                f"font-family: '{theme.FONT_DISPLAY}'; font-size: 15px; color: {theme.TEXT_DIM};"
            )
            self.login_btn.setText("LOG IN WITH EVE")
            self.system_lbl.setText("—")

    def _on_change_region(self) -> None:
        name, ok = QInputDialog.getText(
            self,
            "Change region",
            "Exact EVE region name (e.g. 'The Forge', 'Domain'):",
            text=self.controller.api.region_name,
        )
        if not ok or not name.strip():
            return
        name = name.strip()

        try:
            region_id = self.esi.resolve_region_by_name(name)
        except Exception:
            logger.exception("failed to resolve region name")
            region_id = None

        if region_id is None:
            QMessageBox.warning(
                self, "Unknown region", f"Couldn't find a region named exactly '{name}'."
            )
            return

        self.controller.set_region(region_id, name)

    def _on_region_changed(self) -> None:
        self.region_sub_lbl.setText(f"REGION WATCH — {self.controller.api.region_name.upper()}")

    def _on_feed_updated(self, feed: list[dict]) -> None:
        self._latest_feed = feed

        while self.feed_layout.count() > 1:
            item = self.feed_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for event in feed[:30]:
            try:
                system_name = self.esi.system_name(event["solar_system_id"])
            except Exception:
                logger.exception("failed to resolve system name")
                system_name = str(event["solar_system_id"])

            occurred_at = datetime.fromisoformat(event["occurred_at"])
            age_minutes = (datetime.now(occurred_at.tzinfo) - occurred_at).total_seconds() / 60
            threat = "fresh" if age_minutes < 10 else "recent" if age_minutes < 60 else "stale"

            row = GankFeedRow(
                time_label=occurred_at.strftime("%H:%M"),
                system_name=system_name,
                victim_ship=f"ship type {event['victim']['ship_type_id']}",
                ganker_tag=", ".join(m["entity_name"] for m in event["matched_entities"]) or "unknown",
                jumps=None,
                threat=threat,
            )
            self.feed_layout.insertWidget(self.feed_layout.count() - 1, row)

        self._update_nearest_gank()

    def _on_location_updated(self, location: dict | None) -> None:
        self._my_location = location
        if location is None:
            self.system_lbl.setText("—" if not self.controller.api.is_logged_in else "unknown")
            self._update_nearest_gank()
            return
        try:
            name = self.esi.system_name(location["solar_system_id"])
        except Exception:
            logger.exception("failed to resolve current system name")
            name = str(location["solar_system_id"])
        self.system_lbl.setText(name.upper())
        self._update_nearest_gank()

    def _update_nearest_gank(self) -> None:
        if not self._latest_feed:
            return
        if self._my_location is None:
            self.dist_val.setText("—")
            return

        latest = self._latest_feed[0]
        jumps = self.controller.api.get_jump_distance(
            self._my_location["solar_system_id"], latest["solar_system_id"]
        )
        self.dist_val.setText(str(jumps) if jumps is not None else "—")

        try:
            system_name = self.esi.system_name(latest["solar_system_id"])
        except Exception:
            system_name = str(latest["solar_system_id"])
        tag = ", ".join(m["entity_name"] for m in latest["matched_entities"]) or "unknown"
        self.last_seen_lbl.setText(f"{system_name} · {tag}")
