from __future__ import annotations

import os
from pathlib import Path

# Defaults to the maintainer's hosted instance so a downloaded release
# binary works out of the box with no setup -- override with GANK_API_BASE
# to point at your own self-hosted api instead (e.g. for local dev).
API_BASE = os.environ.get("GANK_API_BASE", "https://gank.mkhcloud.de")

CONFIG_DIR = Path.home() / ".config" / "gank-alert"
TOKEN_FILE = CONFIG_DIR / "token.json"
SETTINGS_FILE = CONFIG_DIR / "settings.json"

DEFAULT_REGION_ID = 10000002
DEFAULT_REGION_NAME = "The Forge"
