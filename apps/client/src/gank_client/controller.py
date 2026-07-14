from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QTimer, Signal

from gank_client.api_client import ApiClient
from gank_client.sso_login import LoginResult, start_login

logger = logging.getLogger("gank_client.controller")

POLL_INTERVAL_MS = 15_000


class Controller(QObject):
    login_changed = Signal()
    feed_updated = Signal(list)
    location_updated = Signal(object)  # dict | None

    def __init__(self) -> None:
        super().__init__()
        self.api = ApiClient()

        self._timer = QTimer(self)
        self._timer.setInterval(POLL_INTERVAL_MS)
        self._timer.timeout.connect(self.refresh)

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

    def refresh(self) -> None:
        try:
            feed = self.api.get_feed()
        except Exception:
            logger.exception("failed to fetch feed")
            feed = []
        self.feed_updated.emit(feed)

        location = None
        if self.api.is_logged_in:
            try:
                location = self.api.get_my_location()
            except Exception:
                logger.exception("failed to fetch location")
        self.location_updated.emit(location)
