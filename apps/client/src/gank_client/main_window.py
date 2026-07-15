from __future__ import annotations

import logging
from datetime import datetime, timedelta
from functools import partial

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
from gank_shared.formatting import format_isk
from gank_shared.tiers import tier_for_age

from gank_client import theme
from gank_client.controller import Controller
from gank_client.sound import SoundPlayer
from gank_client.widgets import GankFeedRow, HudPanel, SectionTitle, fix_transparency

logger = logging.getLogger("gank_client.main_window")

FEED_EXPIRE_HOURS = 6
"""Kills older than this drop out of the feed entirely, same idea as the
bot's 4h alert cutoff but a bit more generous since this is a browsable
history view, not just live alerts."""


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("GANK ALERT")
        self.resize(880, 640)
        self.setMinimumSize(720, 520)

        self.esi = ESIClient(component="client")
        self.controller = Controller()
        self.sound_player = SoundPlayer()

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
        self.controller.new_alert.connect(self.sound_player.play)

        self._latest_feed: list[dict] = []
        self._dismissed_ids: set[int] = set()
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

    def _visible_feed(self) -> list[dict]:
        cutoff = datetime.now().astimezone() - timedelta(hours=FEED_EXPIRE_HOURS)
        return [
            event
            for event in self._latest_feed
            if event["killmail_id"] not in self._dismissed_ids
            and datetime.fromisoformat(event["occurred_at"]) >= cutoff
        ]

    def _dismiss_event(self, killmail_id: int) -> None:
        self._dismissed_ids.add(killmail_id)
        self._render_feed()

    def _on_feed_updated(self, feed: list[dict]) -> None:
        self._latest_feed = feed
        self._render_feed()

    def _render_feed(self) -> None:
        while self.feed_layout.count() > 1:
            item = self.feed_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        visible = self._visible_feed()[:30]
        ids: set[int] = set()
        for event in visible:
            ids.add(event["solar_system_id"])
            ids.add(event["victim"]["ship_type_id"])
            for key in ("character_id", "corporation_id"):
                if event["victim"].get(key):
                    ids.add(event["victim"][key])
            if not event["matched_entities"]:
                final_blow = next((a for a in event["attackers"] if a.get("final_blow")), None)
                if final_blow:
                    for key in ("corporation_id", "alliance_id"):
                        if final_blow.get(key):
                            ids.add(final_blow[key])
        try:
            names = self.esi.resolve_names(list(ids))
        except Exception:
            logger.exception("failed to resolve feed names")
            names = {}

        for event in visible:
            victim = event["victim"]
            system_name = names.get(event["solar_system_id"], str(event["solar_system_id"]))
            ship_name = names.get(victim["ship_type_id"], f"ship type {victim['ship_type_id']}")
            victim_name = names.get(victim.get("character_id"), "unknown pilot")

            location_name = None
            if event.get("location_id"):
                try:
                    location_name = self.esi.resolve_location_name(event["location_id"])
                except Exception:
                    logger.exception("failed to resolve location name")

            if event["matched_entities"]:
                ganker_tag = ", ".join(m["entity_name"] for m in event["matched_entities"])
            else:
                # Not on our curated list, but zKillboard's own heuristic
                # flagged this as a gank -- show who actually did it
                # instead of a bare "unknown".
                final_blow = next((a for a in event["attackers"] if a.get("final_blow")), None)
                ganker_tag = "unknown"
                if final_blow:
                    ganker_tag = (
                        names.get(final_blow.get("alliance_id"))
                        or names.get(final_blow.get("corporation_id"))
                        or "unknown"
                    )

            # occurred_at comes back as UTC from the api -- show it in
            # whatever timezone this PC is set to, not raw UTC.
            occurred_at = datetime.fromisoformat(event["occurred_at"])
            local_time = occurred_at.astimezone()
            age_minutes = (datetime.now(occurred_at.tzinfo) - occurred_at).total_seconds() / 60
            tier = tier_for_age(age_minutes)

            row = GankFeedRow(
                time_label=local_time.strftime("%H:%M"),
                system_name=system_name,
                victim_name=victim_name,
                victim_ship=ship_name,
                ganker_tag=ganker_tag,
                value_str=format_isk(event.get("total_value")),
                attacker_count=len(event["attackers"]),
                location_name=location_name,
                jumps=None,
                tier=tier,
                on_dismiss=partial(self._dismiss_event, event["killmail_id"]),
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
        visible = self._visible_feed()
        if not visible:
            self.dist_val.setText("—")
            self.last_seen_lbl.setText("no data yet")
            return
        if self._my_location is None:
            self.dist_val.setText("—")
            return

        latest = visible[0]
        jumps = self.controller.api.get_jump_distance(
            self._my_location["solar_system_id"], latest["solar_system_id"]
        )
        self.dist_val.setText(str(jumps) if jumps is not None else "—")

        try:
            system_name = self.esi.system_name(latest["solar_system_id"])
        except Exception:
            system_name = str(latest["solar_system_id"])

        if latest["matched_entities"]:
            tag = ", ".join(m["entity_name"] for m in latest["matched_entities"])
        else:
            tag = "unknown"
            final_blow = next((a for a in latest["attackers"] if a.get("final_blow")), None)
            if final_blow:
                fallback_ids = [i for i in (final_blow.get("alliance_id"), final_blow.get("corporation_id")) if i]
                try:
                    names = self.esi.resolve_names(fallback_ids)
                except Exception:
                    names = {}
                tag = (
                    names.get(final_blow.get("alliance_id"))
                    or names.get(final_blow.get("corporation_id"))
                    or "unknown"
                )

        self.last_seen_lbl.setText(f"{system_name} · {tag}")
