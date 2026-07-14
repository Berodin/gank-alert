from __future__ import annotations

import os
from pathlib import Path


class Settings:
    def __init__(self) -> None:
        self.eve_client_id = os.environ["GANK_EVE_CLIENT_ID"]
        self.eve_redirect_uri = os.environ["GANK_EVE_REDIRECT_URI"]
        self.db_path = Path(os.environ.get("GANK_DB_PATH", "gank_alert.sqlite3"))
        self.region_id = int(os.environ.get("GANK_REGION_ID", "10000002"))
        self.scopes = ["esi-location.read_location.v1"]
        self.universe_graph_path = Path(
            os.environ.get(
                "GANK_UNIVERSE_GRAPH_PATH",
                Path(__file__).parents[4] / "packages" / "shared" / "universe_graph.json",
            )
        )


settings = Settings()
