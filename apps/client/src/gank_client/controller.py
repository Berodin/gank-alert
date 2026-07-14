from __future__ import annotations

import logging
from datetime import UTC, datetime

from PySide6.QtCore import QObject, QTimer, Signal

from gank_shared.tiers import tier_for_age

from gank_client.api_client import ApiClient
from gank_client.sso_login import LoginResult, start_login

logger = logging.getLogger("gank_client.controller")

POLL_INTERVAL_MS = 15_000


class Controller(QObject):
    login_changed = Signal()
    region_changed = Signal()
    feed_updated = Signal(list)
    location_updated = Signal(object)  # dict | None
    new_alert = Signal(str)  # tier label, for a kill not seen before this poll

    def __init__(self) -> None:
        super().__init__()
        self.api = ApiClient()

        self._timer = QTimer(self)
        self._timer.setInterval(POLL_INTERVAL_MS)
        self._timer.timeout.connect(self.refresh)

        # Tracks which kills we've already surfaced, so refresh() only
        # fires new_alert for genuinely new arrivals -- not re-fires it
        # for the same kill every 15s, and not for the whole feed on the
        # very first load or right after switching regions.
        self._seen_killmail_ids: set[int] = set()
        self._suppress_alerts_next_refresh = True

    def start(self) -> None:
        self.refresh()
        self._timer.start()

    def begin_login(self) -> None:
        start_login(on_result=self._on_login_result)

    # runs on the loopback server's background thread; Qt marshals the
    # signal emit back onto the GUI thread automatically since this
    # Controller lives there.
    def _on_login_result(self, result: LoginResult | None) -> None:
        if result is None:
            logger.warning("login did not complete")
            return
        self.api.save_login(result.api_token, result.character_id, result.character_name)
        self.login_changed.emit()
        self.refresh()

    def logout(self) -> None:
        self.api.logout()
        self.login_changed.emit()

    def set_region(self, region_id: int, region_name: str) -> None:
        self.api.set_region(region_id, region_name)
        self._seen_killmail_ids = set()
        self._suppress_alerts_next_refresh = True
        self.region_changed.emit()
        self.refresh()

    def refresh(self) -> None:
        try:
            feed = self.api.get_feed()
        except Exception:
            logger.exception("failed to fetch feed")
            feed = []
        self.feed_updated.emit(feed)
        self._check_new_alerts(feed)

        location = None
        if self.api.is_logged_in:
            try:
                location = self.api.get_my_location()
            except Exception:
                logger.exception("failed to fetch location")
        self.location_updated.emit(location)

    def _check_new_alerts(self, feed: list[dict]) -> None:
        current_ids = {event["killmail_id"] for event in feed}
        new_ids = current_ids - self._seen_killmail_ids
        self._seen_killmail_ids = current_ids

        if self._suppress_alerts_next_refresh:
            self._suppress_alerts_next_refresh = False
            return

        for event in feed:
            if event["killmail_id"] not in new_ids:
                continue
            occurred_at = datetime.fromisoformat(event["occurred_at"])
            age_minutes = (datetime.now(UTC) - occurred_at).total_seconds() / 60
            tier = tier_for_age(age_minutes)
            if tier is not None:
                self.new_alert.emit(tier[0])
