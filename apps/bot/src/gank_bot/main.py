from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import tasks

from gank_shared.esi import ESIClient
from gank_shared.tiers import RECENT_MINUTES, tier_for_age

from gank_bot import storage
from gank_bot.embeds import build_embed, collect_ids

logger = logging.getLogger("gank_bot")

POLL_SECONDS = 30

REMINDER_MODE_MAX_POSTS: dict[str, int] = {
    "fresh_only": 1,
    "fresh_recent": 2,
}
"""Max number of times a single kill gets posted to a guild, per its
reminder mode -- STAY WARY reminders are retired entirely in both modes:
past RECENT_MINUTES a kill still ages out visually in the client (color
fade), it just no longer gets a repeated Discord message.

Deliberately keyed on *how many times this kill has posted*, not on
"only post while literally in the FRESH tier" -- zKillboard's own
"ganked" labeling is retroactive and can take much longer than usual
(confirmed in production: one solo gank took 67 minutes, past the
60-minute FRESH cutoff, before we ever saw it as a gank at all). A kill
whose first-ever sighting already lands in RECENT must still get its one
guaranteed post under fresh_only -- the alternative is total silence for
a real gank, which defeats the point of the mode."""
DEFAULT_REMINDER_MODE = "fresh_recent"


def _reminder_allowed(reminder_mode: str, already_posted_count: int) -> bool:
    max_posts = REMINDER_MODE_MAX_POSTS.get(reminder_mode, REMINDER_MODE_MAX_POSTS[DEFAULT_REMINDER_MODE])
    return already_posted_count < max_posts


class GankBot(discord.Client):
    def __init__(self, db_path: Path) -> None:
        super().__init__(intents=discord.Intents.default())
        self.db_path = db_path
        self.esi = ESIClient(component="bot")
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        _register_commands(self.tree, self.db_path, self.esi)
        await self.tree.sync()
        self.poll_gank_events.start()

    async def close(self) -> None:
        self.esi.close()
        await super().close()

    @tasks.loop(seconds=POLL_SECONDS)
    async def poll_gank_events(self) -> None:
        conn = storage.connect(self.db_path)
        try:
            guilds = storage.all_guild_settings(conn)
            # RECENT_MINUTES, not WARY_MINUTES: no reminder mode ever posts
            # a STAY WARY reminder (see REMINDER_MODE_TIERS), so there's no
            # point fetching events older than the latest tier any mode
            # can actually post.
            since_iso = (datetime.now(UTC) - timedelta(minutes=RECENT_MINUTES)).isoformat()

            for guild_row in guilds:
                # One guild's bad channel permissions (etc) must not take
                # down alerts for every other guild, or stop the loop
                # entirely -- discord.ext.tasks.Loop does not auto-restart
                # after an unhandled exception.
                try:
                    await self._post_for_guild(conn, guild_row, since_iso)
                except Exception:
                    logger.exception("failed to post alerts for guild_id=%d", guild_row["guild_id"])
        finally:
            conn.close()

    async def _post_for_guild(self, conn, guild_row, since_iso: str) -> None:
        channel = self.get_channel(guild_row["channel_id"])
        if channel is None:
            logger.warning(
                "channel %d not found for guild %d", guild_row["channel_id"], guild_row["guild_id"]
            )
            return

        rows = storage.events_in_window_for_guild(
            conn, guild_id=guild_row["guild_id"], region_id=guild_row["region_id"], since_iso=since_iso
        )
        if not rows:
            return

        already_posted = storage.posted_tiers_for_guild(conn, guild_id=guild_row["guild_id"])
        posted_counts: dict[int, int] = {}
        for kid, _tier in already_posted:
            posted_counts[kid] = posted_counts.get(kid, 0) + 1
        reminder_mode = guild_row["reminder_mode"]

        # A kill is a repeating reminder, not a one-shot notice: it's
        # posted again each time it crosses into a new staleness tier
        # (FRESH -> RECENT), so people still in the area get nudged as
        # the threat window closes, not just once at t=0. How many times
        # is capped per guild via /setreminders (REMINDER_MODE_MAX_POSTS)
        # -- capped by count, not by which literal tier this is, since a
        # kill's first-ever sighting can itself already land past FRESH
        # (zKillboard's "ganked" labeling is retroactive and sometimes
        # slow) and must still get its one guaranteed post.
        due = []
        for killmail_id, payload in rows:
            event = json.loads(payload)
            occurred_at = datetime.fromisoformat(event["occurred_at"])
            age_minutes = (datetime.now(UTC) - occurred_at).total_seconds() / 60
            tier = tier_for_age(age_minutes)
            if tier is None:
                continue
            label, _ = tier
            if (killmail_id, label) in already_posted:
                continue
            if not _reminder_allowed(reminder_mode, posted_counts.get(killmail_id, 0)):
                continue
            due.append((killmail_id, label, event))

        if not due:
            return

        all_ids: set[int] = set()
        for _, _, event in due:
            all_ids |= collect_ids(event)
        names = self.esi.resolve_names(list(all_ids))

        for killmail_id, label, event in due:
            location_name = None
            if event.get("location_id"):
                location_name = self.esi.resolve_location_name(event["location_id"])
            embed = build_embed(event, names, location_name)
            if embed is not None:
                try:
                    await channel.send(embed=embed)
                except discord.Forbidden:
                    logger.error(
                        "missing permissions to post in channel %d (guild %d) -- check the bot has "
                        "View Channel/Send Messages/Embed Links there. Will retry next cycle.",
                        guild_row["channel_id"],
                        guild_row["guild_id"],
                    )
                    return  # same failure for every remaining event this cycle, stop here
            storage.mark_posted(conn, guild_id=guild_row["guild_id"], killmail_id=killmail_id, tier=label)

    @poll_gank_events.before_loop
    async def _before_poll(self) -> None:
        await self.wait_until_ready()


def _register_commands(tree: app_commands.CommandTree, db_path: Path, esi: ESIClient) -> None:
    @tree.command(name="setregion", description="Choose which EVE region this server gets gank alerts for")
    @app_commands.describe(region="Exact EVE region name, e.g. 'The Forge' or 'Domain'")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setregion(interaction: discord.Interaction, region: str) -> None:
        region_id = esi.resolve_region_by_name(region)
        if region_id is None:
            await interaction.response.send_message(
                f"Couldn't find a region named exactly '{region}'. "
                "Region names are case-sensitive, e.g. 'The Forge', 'Domain', 'Heimatar'.",
                ephemeral=True,
            )
            return

        conn = storage.connect(db_path)
        try:
            storage.set_guild_region(
                conn,
                guild_id=interaction.guild_id,
                channel_id=interaction.channel_id,
                region_id=region_id,
                region_name=region,
            )
        finally:
            conn.close()

        await interaction.response.send_message(
            f"This channel will now get gank alerts for **{region}**."
        )

    @setregion.error
    async def setregion_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "You need the 'Manage Server' permission to set the region.", ephemeral=True
            )
        else:
            logger.exception("setregion command failed", exc_info=error)
            await interaction.response.send_message("Something went wrong.", ephemeral=True)

    @tree.command(
        name="setreminders", description="Choose how many times this channel gets reminded about an ongoing gank"
    )
    @app_commands.describe(mode="How many staleness reminders to post per gank")
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="Fresh only -- single alert, no reminder", value="fresh_only"),
            app_commands.Choice(name="Fresh + Recent -- one reminder within 2h", value="fresh_recent"),
        ]
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setreminders(interaction: discord.Interaction, mode: app_commands.Choice[str]) -> None:
        conn = storage.connect(db_path)
        try:
            updated = storage.set_guild_reminder_mode(
                conn, guild_id=interaction.guild_id, reminder_mode=mode.value
            )
        finally:
            conn.close()

        if not updated:
            await interaction.response.send_message(
                "This channel hasn't been set up yet -- run /setregion first.", ephemeral=True
            )
            return

        await interaction.response.send_message(f"Reminder mode set to **{mode.name}**.")

    @setreminders.error
    async def setreminders_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "You need the 'Manage Server' permission to change this.", ephemeral=True
            )
        else:
            logger.exception("setreminders command failed", exc_info=error)
            await interaction.response.send_message("Something went wrong.", ephemeral=True)


def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    token = os.environ["DISCORD_BOT_TOKEN"]
    db_path = Path(os.environ.get("GANK_DB_PATH", "gank_alert.sqlite3"))

    bot = GankBot(db_path=db_path)
    bot.run(token)


if __name__ == "__main__":
    run()
