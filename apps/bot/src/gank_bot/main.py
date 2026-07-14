from __future__ import annotations

import json
import logging
import os
import sqlite3
from pathlib import Path

import discord
from discord.ext import tasks

logger = logging.getLogger("gank_bot")

POLL_SECONDS = 10


class GankBot(discord.Client):
    def __init__(self, db_path: Path, channel_id: int) -> None:
        super().__init__(intents=discord.Intents.default())
        self.db_path = db_path
        self.channel_id = channel_id

    async def setup_hook(self) -> None:
        self.poll_gank_events.start()

    @tasks.loop(seconds=POLL_SECONDS)
    async def poll_gank_events(self) -> None:
        channel = self.get_channel(self.channel_id)
        if channel is None:
            logger.warning("channel %d not found (yet)", self.channel_id)
            return

        conn = sqlite3.connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT killmail_id, payload_json FROM gank_events "
                "WHERE posted_discord = 0 ORDER BY occurred_at ASC"
            ).fetchall()

            for killmail_id, payload_json in rows:
                event = json.loads(payload_json)
                await channel.send(embed=_build_embed(event))
                conn.execute(
                    "UPDATE gank_events SET posted_discord = 1 WHERE killmail_id = ?",
                    (killmail_id,),
                )
                conn.commit()
        finally:
            conn.close()

    @poll_gank_events.before_loop
    async def _before_poll(self) -> None:
        await self.wait_until_ready()


def _build_embed(event: dict) -> discord.Embed:
    attacker_tags = ", ".join(m["entity_name"] for m in event["matched_entities"])
    embed = discord.Embed(
        title="Gank detected",
        description=f"Victim ship type `{event['victim']['ship_type_id']}` "
        f"destroyed in system `{event['solar_system_id']}`",
        color=discord.Color.red(),
    )
    embed.add_field(name="Attacker group(s)", value=attacker_tags or "unknown")
    embed.add_field(name="Killmail", value=f"[zKillboard](https://zkillboard.com/kill/{event['killmail_id']}/)")
    return embed


def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    token = os.environ["DISCORD_BOT_TOKEN"]
    channel_id = int(os.environ["DISCORD_CHANNEL_ID"])
    db_path = Path(os.environ.get("GANK_DB_PATH", "gank_alert.sqlite3"))

    bot = GankBot(db_path=db_path, channel_id=channel_id)
    bot.run(token)


if __name__ == "__main__":
    run()
