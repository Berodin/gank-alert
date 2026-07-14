# gank-alert

Region-scoped EVE Online gank tracker: a Discord bot that posts alerts, and
a desktop app people run to see live distance to the last known gank.

Always scoped to exactly one region (configured via `GANK_REGION_ID`), never
a system or the whole universe.

## How it works

- **Discovery**: [zKillboard R2Z2](https://github.com/zKillboard/zKillboard/wiki/API-(R2Z2))
  -- a sequence-numbered feed of every killmail in the game (RedisQ's
  replacement, sunset 2026-05-31). No region filter server-side, so we filter
  client-side using ESI's static system → constellation → region lookup
  (cached forever, it never changes).
- **Classification**: attacker corp/alliance IDs are matched against a
  maintained ganker list (`packages/shared/ganker_list.seed.json`, seeded
  with CODE. and Snuffed Out -- verify/extend this yourself). We match on
  *attackers*, not the victim -- a ganker corp getting CONCORD'd shows up as
  a separate killmail where that corp is the victim, which is evidence
  CONCORD responded, not the gank itself.
- **Storage**: SQLite (WAL mode), shared via a Docker volume between the
  ingester, bot, and api. Deliberately not Postgres -- single background
  writer, light read volume, one less service to run on a small box. Revisit
  if that stops being true.

## Structure

```
apps/
  ingester/   # R2Z2 poller -> region filter -> ganker classification -> SQLite
  bot/        # Discord bot, polls SQLite for unposted gank_events, posts embeds
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

- **bot**: needs a Discord bot token + channel ID (`DISCORD_BOT_TOKEN`,
  `DISCORD_CHANNEL_ID`) from https://discord.com/developers/applications.
- **api** / **client** login: needs an EVE developer app
  (https://developers.eveonline.com) of type **public client** (PKCE, no
  secret) with scope `esi-location.read_location.v1` and redirect URI
  matching `GANK_EVE_REDIRECT_URI` (must point at `api`'s
  `/auth/eve/callback`, not the client).
- **ganker list**: only 2 seed entries (CODE., Snuffed Out), verified via
  ESI but not curated -- expand `ganker_list.seed.json` with whatever groups
  you actually want to track.

## Local dev

```
uv sync --all-packages
uv run --package gank-ingester gank-ingester   # runs immediately, no auth needed
uv run --package gank-api gank-api             # needs GANK_EVE_CLIENT_ID / GANK_EVE_REDIRECT_URI
uv run --package gank-bot gank-bot             # needs DISCORD_BOT_TOKEN / DISCORD_CHANNEL_ID
uv run --package gank-client gank-client       # opens the desktop app window
```

## Deploy

`deploy/docker-compose.yml` runs `ingester` + `bot` + `api` on one box (no
public ports needed for ingester/bot -- outbound only). `api` joins the
existing shared Traefik network (`lizard-intel_default`, same pattern as
`conduwuit-docker` and `lizard-intel`) so it just needs a `GANK_API_DOMAIN`
subdomain, no separate Traefik/Cloudflare setup.

```
cp deploy/.env.example deploy/.env   # fill in values
cd deploy && docker compose up -d --build
```

`gank-client` is not deployed -- `.github/workflows/ci.yml` builds it per-OS
(Windows/Linux) via PyInstaller (`apps/client/gank_client.spec`) on every
push and, on a `v*` tag, attaches both binaries to a GitHub release. The
same workflow builds and pushes `ingester`/`bot`/`api` images to
`ghcr.io/<repo>-<app>` on pushes to `main`.
