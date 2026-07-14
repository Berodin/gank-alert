from __future__ import annotations

import os
from pathlib import Path

API_BASE = os.environ.get("GANK_API_BASE", "http://127.0.0.1:8000")

CONFIG_DIR = Path.home() / ".config" / "gank-alert"
TOKEN_FILE = CONFIG_DIR / "token.json"
SETTINGS_FILE = CONFIG_DIR / "settings.json"

DEFAULT_REGION_ID = 10000002
DEFAULT_REGION_NAME = "The Forge"
