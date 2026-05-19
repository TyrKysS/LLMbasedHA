# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Home Assistant add-on repository. Each subdirectory is a self-contained HA add-on. Currently contains one add-on: `ha_device_monitor` — a real-time dashboard displaying all HA entity states, with a live change log, domain filtering, and full-text search.

## Running / building

The add-on runs inside HA's supervisor. For local testing, build and run with Docker:

```bash
cd ha_device_monitor
docker build -t ha_device_monitor .
docker run -e SUPERVISOR_TOKEN=<token> -p 8099:8099 ha_device_monitor
```

The app can also be run directly (requires `SUPERVISOR_TOKEN` in environment):

```bash
cd ha_device_monitor/app
pip install -r requirements.txt
SUPERVISOR_TOKEN=<token> python3 main.py
```

## Installing as an HA add-on

Copy this repository to `/addons/` on the HA host, then in HA: Settings → Add-ons → Add-on store → ⋮ → Check for updates. The add-on appears under Local add-ons.

## Architecture

**`ha_device_monitor/`**
- `config.yaml` — HA add-on manifest (slug, version, supported architectures, API permissions, ingress port 8099)
- `Dockerfile` — `python:3.12-alpine`, installs `requirements.txt`, runs `main.py`
- `app/main.py` — the entire backend; single `aiohttp` async app
- `app/templates/dashboard.html` — single-page frontend with vanilla JS WebSocket client

**Data flow in `main.py`:**
1. On startup, `fetch_all_states()` calls `GET http://supervisor/core/api/states` to populate `states_cache` (dict keyed by `entity_id`)
2. `listen_ha_events()` runs as a background task, connecting to `ws://supervisor/core/api/websocket` and subscribing to `state_changed` events. It auto-reconnects on failure.
3. Each incoming HA event calls `classify_entity()` (maps domain → typed display dict), updates `states_cache`, logs the change as JSON to stdout, and calls `broadcast()` to push the update to all connected browser WebSocket clients.
4. Browser clients connect to `/ws`, receive the full `states_cache` on init, then receive individual `state_changed` messages in real time.

**Key globals in `main.py`:**
- `states_cache: dict[str, dict]` — in-memory entity state store; the only source of truth
- `ws_clients: set[web.WebSocketResponse]` — connected browser WebSocket sessions

**HTTP routes:** `GET /` (Jinja2 dashboard), `GET /api/states` (JSON snapshot), `GET /ws` (WebSocket upgrade)

**Auth:** `SUPERVISOR_TOKEN` env var (set automatically by HA supervisor) is used as Bearer token for all calls to the supervisor API.

## Adding a new add-on

Each add-on needs at minimum: a `config.yaml`, a `Dockerfile`, and an `app/` directory. Follow the structure of `ha_device_monitor` as a template. The `repository.yaml` at the root does not need to be modified.
