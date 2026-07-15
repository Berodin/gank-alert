# gank-alert

EVE Online gank tracker: a Discord bot that posts alerts, and a desktop app
people run to see live distance to the last known gank.

Each consumer picks a **single region** (never a system, never multiple at
once) -- but they pick independently: every Discord server running the bot
sets its own region with `/setregion`, and each desktop app user sets theirs
with the "Change region" button (stored locally, not on the server). The
ingester underneath watches the whole galaxy for the ganker list and tags
every match with its region, so no consumer is limited to whatever region
someone else picked, and `api` itself is entirely region-agnostic.

## How it works

- **Discovery**: [zKillboard R2Z2](https://github.com/zKillboard/zKillboard/wiki/API-(R2Z2))
  -- a sequence-numbered feed of every killmail in the game (RedisQ's
  replacement, sunset 2026-05-31). Global firehose, no region filter
  server-side. If the ingester is ever down long enough that its resume
  cursor points at an already-purged sequence (R2Z2 only guarantees 24h
  retention), a stuck-sequence detector jumps forward to the live edge
  after ~10 minutes rather than hanging forever waiting for a file that's
  gone.
- **Classification**: highsec-only, hard filter -- ganking is inherently a
  highsec/CONCORD phenomenon, so a listed group doing normal PvP in
  null/lowsec never counts (checked via `zkb.labels`' `loc:highsec`, free,
  no ESI call). Within highsec, two independent ways to count as a gank:
  attacker corp/alliance IDs matched against a maintained list
  (`packages/shared/ganker_list.seed.json`, seeded with CODE., Snuffed
  Out, and Safety. -- verify/extend this yourself), *or* zKillboard's own
  `ganked` label agreeing (catches one-off/unlisted gankers too -- the
  bot/client then fall back to showing the actual attacker corp/alliance
  from the killmail instead of a bare "unknown"). We match on *attackers*,
  not the victim -- a ganker corp getting CONCORD'd shows up as a separate
  killmail where that corp is the victim, which is evidence CONCORD
  responded, not the gank itself. Classification happens before the ESI
  region lookup (cheap, in-memory/label match first), so the ingester
  only pays for a region resolution on kills that actually matter.
- **Alerts are reminders, not one-shot notices**: a kill is posted again
  each time it ages into a new tier -- 🔴 FRESH (<1h), 🟠 RECENT (<2h),
  🟡 STAY WARY (<4h) -- so people still in the area get nudged as the
  threat window closes, not just once at detection time. Each (guild,
  kill, tier) combination fires exactly once; nothing is posted past 4h,
  including during backlog catch-up after downtime.
- **Storage**: SQLite (WAL mode), shared via a Docker volume between the
  ingester, bot, and api. Deliberately not Postgres -- single background
  writer, light read volume, one less service to run on a small box. Revisit
  if that stops being true.

## Structure

```
apps/
  ingester/   # R2Z2 poller -> ganker classification -> region tagging -> SQLite
  bot/        # Discord bot: /setregion per-guild, posts tiered gank embeds
  api/        # FastAPI: EVE SSO (PKCE) login, character location ingest, region feed
  client/     # Desktop app (Windows + Linux): PySide6, EVE HUD-styled UI
packages/
  shared/     # ESI client, EVE SSO/PKCE, schemas, ganker list loader
deploy/
  Dockerfile, docker-compose.yml, .env.example
```

## Status

Runnable now, without any credentials:

```
uv run --package gank-ingester gank-ingester
```

Polls R2Z2 live, resolves regions, classifies against the seed ganker list,
persists a resume cursor. Verified working end to end against production
R2Z2 and ESI.

`packages/shared/universe_graph.json` (stargate adjacency for all ~5,268
known-space systems) is built and committed -- `api`'s `/jump-distance` does
a real BFS shortest-path over it, verified against known routes (Jita ->
Amarr = 11 jumps). Rebuild with `uv run --package gank-shared python -m
gank_shared.universe_graph <path>` if CCP adds/removes stargates (rare,
maybe once or twice a year with expansions) -- it's ~21,500 ESI calls, takes
a few minutes.

`gank-client` is wired to `api` for real: SSO login (PKCE, via a system
browser + one-shot localhost loopback server -- necessary because EVE's
fixed redirect URI points at `api`, not the client, so `api` hands the
issued token back to the client's loopback listener), the region feed, and
jump-distance are all live calls, verified end-to-end against a running
`api` instance. `api` now polls each linked character's location in the
background (refreshing their EVE SSO token every cycle, since EVE rotates
refresh tokens on use) rather than having the client push it -- keeps raw
EVE OAuth tokens off the client machine entirely, only api's own opaque
token round-trips there.

Needs your own credentials/setup before it does anything useful end-to-end:

- **bot**: needs a Discord bot token (`DISCORD_BOT_TOKEN`) from
  https://discord.com/developers/applications. When generating the invite
  link, include the `applications.commands` OAuth2 scope or `/setregion`
  won't show up. Each server picks its region (and which channel gets
  alerts -- wherever `/setregion` was run) at runtime; requires the "Manage
  Server" permission to run.
- **api** / **client** login: needs an EVE developer app
  (https://developers.eveonline.com) of type **public client** (PKCE, no
  secret) with scope `esi-location.read_location.v1` and redirect URI
  matching `GANK_EVE_REDIRECT_URI` (must point at `api`'s
  `/auth/eve/callback`, not the client).
- **ganker list**: only 3 seed entries (CODE., Snuffed Out, Safety.),
  verified via ESI but not exhaustively curated -- expand
  `ganker_list.seed.json` with whatever groups you actually want to track.

## Local dev

```
uv sync --all-packages
uv run --package gank-ingester gank-ingester   # runs immediately, no auth needed
uv run --package gank-api gank-api             # needs GANK_EVE_CLIENT_ID / GANK_EVE_REDIRECT_URI
uv run --package gank-bot gank-bot             # needs DISCORD_BOT_TOKEN, then /setregion in a server
uv run --package gank-client gank-client       # opens the desktop app window
```

## Testing

```
uv sync --all-packages --group dev
uv run --group dev pytest -v
```

64 tests, no live network calls (ESI/R2Z2 mocked with `respx`, Discord never
constructed, sqlite via `tmp_path`). Covers the parts that are easy to get
subtly wrong and hard to eyeball: ganker-list classification (attackers
only, never the victim), the R2Z2 stuck-cursor jump using a fake clock so
it doesn't take 10 real minutes, PKCE/JWT handling, BFS jump-distance,
per-guild region filtering and posted-tracking, embed tiering/staleness,
and the `/feed` + `/jump-distance` HTTP contracts. Runs in CI on every push
and PR; image/client builds won't run if it fails. No coverage for the Qt
GUI itself or an actual Discord connection -- those still need a manual
check (see below).

## Deploy

`deploy/docker-compose.yml` is fully self-contained -- it bundles its own
Traefik (Let's Encrypt via HTTP challenge) and doesn't depend on any other
project's infrastructure. `ingester` and `bot` need no public ports at all
(outbound only); only `api` is exposed, on `GANK_API_DOMAIN`. Point that
domain's DNS at the box and set `ACME_EMAIL` and you're done -- no manual
Traefik/Cloudflare setup required.

```
cp deploy/.env.example deploy/.env   # fill in values
cd deploy && docker compose up -d --build
```

`gank-client` is not deployed -- `.github/workflows/ci.yml` builds it per-OS
(Windows/Linux) via PyInstaller (`apps/client/gank_client.spec`) on every
push and, on a `v*` tag, attaches both binaries to a GitHub release. The
same workflow builds and pushes `ingester`/`bot`/`api` images to
`ghcr.io/<repo>-<app>` on pushes to `main`.
