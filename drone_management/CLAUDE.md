# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

All commands assume the venv is active (`source .venv/bin/activate`) and you are in `drone_management/`.

| Task | Command |
|---|---|
| First-time setup | `python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"` |
| Apply migrations | `alembic upgrade head` |
| New migration (autogenerate) | `alembic revision --autogenerate -m "<msg>"` |
| Run service | `uvicorn app.main:app --reload --host 127.0.0.1 --port 8000` |
| Run mock drone | `python -m mock_drone --target 127.0.0.1:14550 --listen 0.0.0.0:14551` |
| All tests | `pytest -q` |
| Single test file | `pytest tests/test_sim_state_machine.py -q` |
| Single test by name | `pytest -q -k test_arm_records_pending_then_accepted` |

The service serves the dashboard at `/` and the OpenAPI docs at `/docs`.

Configuration is via env vars or `.env` (see `.env.example`). Notable: `DB_URL`, `MAVLINK_BIND_PORT` (service listens for telemetry), `DRONE_PORT` (mock drone listens for commands), `HTTP_HOST`/`HTTP_PORT`, `GOOGLE_MAPS_API_KEY` + `GOOGLE_MAPS_MAP_ID` (dashboard map).

For deployment to a remote pod see `RUNPOD_INSTRUCTIONS.txt`.

## Architecture

Three components, one process boundary. The mock drone runs as a **separate Python process** that communicates with the service over **loopback UDP using MAVLink** (not HTTP/WebSocket). When debugging "the drone isn't showing up", the first thing to check is that both processes are running and their UDP port pair is matched (`MAVLINK_BIND_PORT` on the service must equal `--target` on the mock drone).

```
mock_drone process  --MAVLink/UDP-->  FastAPI service  --WebSocket-->  browser
                    <--MAVLink/UDP--                   <--REST----
                                              |
                                         SQLite (WAL)
```

### MAVLink ↔ asyncio bridge (the load-bearing piece)

`pymavlink` is blocking. `app/mavlink_link.py` runs `recv_match()` in a **dedicated thread** and crosses messages back to the event loop via `loop.call_soon_threadsafe(callback, parsed_msg)`. Outbound writes go through `await asyncio.to_thread(...)` behind a `threading.Lock`. Two separate `mavutil.mavlink_connection` objects are used — `udpin:` for ingest and `udpout:` for command transmission. Mistakes here cause silent message loss; never call `asyncio.Queue.put_nowait` directly from the reader thread.

### Telemetry bus + DB writer

`app/telemetry_bus.py` is the central pub/sub. `bus.ingest(msg)` is the single entry point on the asyncio side; it (1) updates an in-memory `DroneState` per `system_id`, (2) broadcasts the new state to all WebSocket subscribers immediately, and (3) appends to a row buffer. A separate `_flush_loop` coroutine writes batched rows to SQLite every 500 ms. **WebSocket fan-out must never await the DB write** — that's the contract that keeps high-rate telemetry from stalling subscribers.

To keep DB volume sane, telemetry rows are persisted only on `HEARTBEAT` (1 Hz) — even though the WebSocket stream emits on every frame (5–10 Hz).

### Command + ACK correlation

`app/command_service.py` issues `COMMAND_LONG` and waits for the matching `COMMAND_ACK`. The `pending: dict[mav_cmd_id, asyncio.Future]` is fulfilled inside `handle_message` when an ACK arrives. The on_message callback set up in `app/main.py`'s lifespan dispatches **every** parsed MAVLink message to both `bus.ingest` and `cmd_service.handle_message`.

`goto` is special: it uses `SET_POSITION_TARGET_GLOBAL_INT` which has no COMMAND_ACK in the MAVLink spec, so the service writes `ACCEPTED` immediately after sending.

### Mock drone

`mock_drone/sim.py` is a deterministic state machine — `tick(dt)` is purely functional given current state, and `__main__.py` calls it at ~20 Hz. The sim itself doesn't know about MAVLink; `mav_io.py` adapts state into MAVLink frames and parses inbound `COMMAND_LONG` / `SET_POSITION_TARGET_GLOBAL_INT`. Tests in `tests/test_sim_state_machine.py` exercise the sim directly, no MAVLink needed.

### DB module access pattern

`app/db.py` exposes `engine` and `SessionLocal`. **Other modules must import via `from . import db as _db` and use `_db.SessionLocal()` at call time**, not `from .db import SessionLocal`. The test fixture in `tests/conftest.py` swaps `db.engine` and `db.SessionLocal` to point at a temp SQLite file per test; rebinding the symbol at import time would defeat that.

### MAVLink dialect

The dialect is pinned to `ardupilotmega` and MAVLink v2 via env vars set at the top of `mavlink_link.py` and `mock_drone/mav_io.py` (`MAVLINK_DIALECT=ardupilotmega`, `MAVLINK20=1`) **before** any pymavlink import. Custom mode integers used (`MANUAL=0`, `AUTO=10`, `RTL=6`) are ArduPilot-specific — switching to PX4 requires changing both the service's `ARDUPILOT_MODE_BY_INT` (in `telemetry_bus.py`) and the sim's `Mode` enum.

### Dashboard map (Google Maps + Pegman)

The dashboard uses **Google Maps JavaScript API in vector mode** (Leaflet was removed). The browser fetches `GET /api/config` first to retrieve `google_maps_api_key` + `google_maps_map_id`, then dynamically injects the Maps SDK (with `libraries=places`) using that key. If the key env var is empty the dashboard surfaces a hint message and skips loading; the rest of the panel keeps functioning. The `mapId` enables Vector + Tilt + Rotation (3D buildings) — created in Google Cloud Console → Map Management. Pegman / Street View is enabled via `streetViewControl: true` and replaces the map area on demand. View toggles in the panel switch between hybrid/roadmap/satellite and flip the tilt 0 ↔ 67.5°.

The Navigate panel uses **Google Directions API + Places Autocomplete** to plan road-following journeys. Both APIs must be enabled in the same Cloud project that owns the API key. The flow: From + To addresses → POST `/api/drones/{id}/commands/teleport` (sim-only, ferries lat/lon via `MAV_CMD_USER_1`) → DirectionsService.route() → thinned waypoint queue → sequential `goto` posts as the drone reaches each point (ARRIVAL_TOL_M = 8 m). The existing map-click goto stays as a separate "dodge" flow (straight-line, no routing).

### CUA (Northstar) integration

The `cua/` package lives next to `app/` and `mock_drone/`. It runs on the user's Mac (CLI: `python -m cua "<goal>"` from `drone_management/`) and drives the **public** dashboard URL through a Lightcone-hosted virtual desktop using the `tzafon.northstar-cua-fast` model. Each CUA step (annotated PNG + action label) is POSTed to `/api/cua/step`, broadcast over the existing telemetry bus as `{"type": "cua_step", ...}`, and rendered in the right-side **Northstar (CUA)** panel.

Files of note:
- `cua/runner.py` — the CUA loop (ported from `Northstar/_cua.py` + `Northstar/visualize.py`).
- `cua/annotate.py` — PIL-based screenshot annotation (red circle on click, banner on type/key/navigate).
- `cua/streamer.py` — best-effort POST client; never raises on failure.
- `cua/tasks.py` — three pre-canned demo tasks (takeoff-land, sf-tour, street-view).
- `app/routers/cua.py` — `POST /api/cua/step` endpoint.
- `docs/CUA_DEMO.md` — operator guide and troubleshooting.

Install on Mac: `pip install -e ".[cua,dev]"`. Pod doesn't need the `[cua]` extra; only the `/api/cua/step` endpoint and dashboard panel changes need to be deployed there.

### v2 / out of scope

ALFA dataset replay (CSV-based, no ROS) and GPU-backed anomaly detection are documented in `RUNPOD_INSTRUCTIONS.txt` and the plan file under `~/.claude/plans/`. v1 deliberately excludes both. The service is designed to host a future `app/alfa_replay.py` ingestor that pushes synthetic frames through `bus.ingest` — preserve that entry point when refactoring.
