"""Shared User-Agent construction per ESI and zKillboard best-practice guidelines.

Both require a non-blank User-Agent identifying the app and a contact method
(email, repo URL, etc). See:
- https://developers.eveonline.com (ESI best practices)
- https://github.com/zKillboard/zKillboard/wiki
"""

APP_NAME = "gank-alert"
APP_VERSION = "0.1.0"
CONTACT = "1994freeway@gmail.com"
SOURCE_URL = "https://github.com/makruse/gank-alert"


def build_user_agent(component: str) -> str:
    """component: e.g. 'ingester', 'bot', 'api', 'client'."""
    return f"{APP_NAME}-{component}/{APP_VERSION} ({CONTACT}; +{SOURCE_URL})"
