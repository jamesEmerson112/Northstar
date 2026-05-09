Last updated: 2026-05-09 (rev 2)

# Session Log

## 1. Project overview

`drone_management` is a v1 bidirectional drone telemetry and management service. A FastAPI process speaks MAVLink v2 (`ardupilotmega` dialect) over loopback UDP to a separate mock-drone Python process, fans live telemetry out to browsers over WebSocket, exposes REST endpoints for command issue/ACK, and persists heartbeat-rate rows to SQLite. The browser dashboard renders the drone on a Google Maps Vector map with Pegman/Street View, a panel of arm/disarm/takeoff/land/mode/goto controls, and a click-to-goto interaction.

## 2. What's working today

- Bidirectional MAVLink/UDP transport: ingest on `udpin:` and command transmit on `udpout:` via two `mavutil.mavlink_connection` objects (`app/mavlink_link.py`).
- FastAPI service exposing REST (`/api/drones`, `/api/drones/{id}/commands/*`, `/api/config`) and a `/ws/telemetry` WebSocket; OpenAPI at `/docs`, dashboard at `/`.
- Telemetry pub/sub bus that updates per-`system_id` `DroneState`, broadcasts to WebSocket subscribers, and batches DB writes on a 500 ms `_flush_loop` (`app/telemetry_bus.py`).
- SQLite persistence in WAL mode via SQLAlchemy + aiosqlite, with Alembic migrations; rows are persisted only on `HEARTBEAT` (1 Hz) while the WebSocket fans out at frame rate (5–10 Hz).
- Command + ACK correlation through a `pending: dict[mav_cmd_id, asyncio.Future]` map; `goto` (`SET_POSITION_TARGET_GLOBAL_INT`) is short-circuited to `ACCEPTED` because the spec issues no `COMMAND_ACK` (`app/command_service.py`).
- Mock drone process: deterministic state machine `tick(dt)` at ~20 Hz, MAVLink adaptation in `mock_drone/mav_io.py`, runs as `python -m mock_drone --target ... --listen ...`.
- Google Maps dashboard with Vector mode (`mapId`), Hybrid/Map/Satellite/Tilt 3D toggles, drone marker rotated from `heading_deg`, polyline trail (max 600 points), Pegman drag-to-Street-View, and click-to-goto.
- RunPod deployment via tmux + the pod proxy URL `https://<pod-id>-8000.proxy.runpod.net`, optionally tunneled via SSH `-L`.

## 3. Architecture

```
mock_drone process  --MAVLink/UDP-->  FastAPI service  --WebSocket-->  browser
                    <--MAVLink/UDP--                   <--REST-------
                                              |
                                         SQLite (WAL)
```

Three components, one process boundary. The mock drone is a separate Python process; it reaches the service over loopback UDP only — never HTTP. Inside the service, `app/telemetry_bus.py` is the in-process pub/sub: `bus.ingest(msg)` is the single entry point on the asyncio side and is responsible for state update, WebSocket broadcast, and DB row buffering. The reader thread in `mavlink_link.py` crosses messages back to the loop via `loop.call_soon_threadsafe`; outbound writes use `asyncio.to_thread` behind a `threading.Lock`. The `on_message` callback wired in `app/main.py`'s lifespan dispatches every parsed frame to both `bus.ingest` and `cmd_service.handle_message`.

## 4. Recent change: Google Maps Level 1 swap

The dashboard was migrated from Leaflet to the Google Maps JavaScript API in **Vector mode** so the map can tilt and rotate (3D buildings) and host Pegman/Street View. Concretely:

- `app/main.py` exposes `GET /api/config` returning `{google_maps_api_key, google_maps_map_id}`. The browser calls this first, then dynamically injects `https://maps.googleapis.com/maps/api/js?key=...&v=weekly&callback=initMap`.
- The Map ID is what enables Vector + Tilt + Rotation; it is created in Google Cloud Console → Map Management and supplied via `GOOGLE_MAPS_MAP_ID`. Without the Map ID the page still loads, but tilt/rotate behavior degrades.
- If `GOOGLE_MAPS_API_KEY` is empty the dashboard surfaces a hint ("GOOGLE_MAPS_API_KEY not set on server") and skips loading; REST/WS continue to function.
- Panel view-toggle buttons set the map type: **Hybrid** (default), **Map** (roadmap), **Satellite**, plus **Tilt 3D** which flips `map.getTilt()` between 0° and 67.5°.
- `streetViewControl: true` enables **Pegman**: drag the orange figure onto a glowing-blue road to enter Street View; click the X to return.
- Tilt/rotate gesture: hold **Shift** and two-finger drag on the map (or right-click drag with a mouse).
- Click-to-goto: tick the "Goto on map click" checkbox, click a point, enter altitude in meters AGL when prompted; sends `POST /api/drones/{id}/commands/goto` with `{lat, lon, alt_m}`.

End-user walkthrough lives in `docs/MAP_GUIDE.md`.

## 5. Required env vars

| Variable | Purpose | Default | Where set |
|---|---|---|---|
| `DB_URL` | SQLAlchemy async URL for SQLite (or other) | `sqlite+aiosqlite:///./drone_management.db` | `.env` / `app/config.py` |
| `MAVLINK_BIND_HOST` | Service UDP bind host for telemetry ingest | `0.0.0.0` | `.env` / `app/config.py` |
| `MAVLINK_BIND_PORT` | Service UDP bind port; must match mock drone `--target` | `14550` | `.env` / `app/config.py` |
| `DRONE_HOST` | Host the service sends commands to | `127.0.0.1` | `.env` / `app/config.py` |
| `DRONE_PORT` | Port the mock drone listens on for commands | `14551` | `.env` / `app/config.py` |
| `HTTP_HOST` | FastAPI bind host | `127.0.0.1` | `.env` / `app/config.py` |
| `HTTP_PORT` | FastAPI bind port | `8000` | `.env` / `app/config.py` |
| `GCS_SYSTEM_ID` | MAVLink GCS system id | `255` | `app/config.py` |
| `GCS_COMPONENT_ID` | MAVLink GCS component id | `190` | `app/config.py` |
| `MAVLINK20` | Force MAVLink v2 wire format (set before pymavlink import) | `1` | `.env`, `mavlink_link.py`, `mock_drone/mav_io.py` |
| `MAVLINK_DIALECT` | MAVLink dialect (ArduPilot-only modes assumed) | `ardupilotmega` | `.env`, `mavlink_link.py`, `mock_drone/mav_io.py` |
| `GOOGLE_MAPS_API_KEY` | Browser-visible Maps JS API key | `""` | `.env` / `app/config.py` (served via `/api/config`) |
| `GOOGLE_MAPS_MAP_ID` | Cloud-configured Map ID enabling Vector / Tilt | `""` | `.env` / `app/config.py` (served via `/api/config`) |

## 6. Deployment story

### Local dev

```
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # then edit
alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
# in a second terminal:
python -m mock_drone --target 127.0.0.1:14550 --listen 0.0.0.0:14551
```

Open `http://127.0.0.1:8000/`. Tests: `pytest -q`.

### RunPod (canonical runbook in `RUNPOD_INSTRUCTIONS.txt`)

- Pod image: `runpod/pytorch:2.4.0-py3.11-cuda12.4.1` (or any `python>=3.11`); volume mounted at `/workspace`; expose port `8000`.
- Clone into `/workspace/Northstar/drone_management`, set up venv, write `.env` (note `DB_URL=sqlite+aiosqlite:////workspace/drone_management.db` and `HTTP_HOST=0.0.0.0`), `alembic upgrade head`.
- Start both processes in a tmux session: pane 1 runs `uvicorn ...`, pane 2 runs `python -m mock_drone --target 127.0.0.1:14550 --listen 0.0.0.0:14551`.
- Reach the dashboard at `https://<pod-id>-8000.proxy.runpod.net`.

#### Public dashboard URL via the pod's HTTP proxy

Adding `8000` to the pod's **Expose HTTP Ports** setting (alongside `8888` for Jupyter) makes the Connect tab show `Port 8000 → HTTP Service` as Ready. The URL `https://<pod-id>-8000.proxy.runpod.net` is then reachable from any browser without an SSH tunnel.

Caveat: the dashboard ships with **no auth**. Anyone holding the URL can call `POST /api/drones/.../commands/arm` (and every other command). Acceptable for the planned CUA experiments; for production this needs a token or auth layer.

#### Pod-restart recovery

A RunPod stop/start preserves `/workspace` (so `.venv` and `.env` survive) but kills every running process and resets some in-memory state. After a restart, re-run:

```
apt-get update && apt-get install -y tmux
cd /workspace/Northstar/drone_management && source .venv/bin/activate && alembic upgrade head
# then re-create the tmux session per RUNPOD_INSTRUCTIONS.txt step 6
```

#### Pod-restart DNS gotcha

After a restart, `/etc/resolv.conf` came back pointed at `nameserver 127.0.0.11` (Docker's internal resolver) and external DNS lookups failed (`Could not resolve host: github.com`). Fix:

```
echo "nameserver 8.8.8.8" > /etc/resolv.conf
echo "nameserver 1.1.1.1" >> /etc/resolv.conf
```

This override is in-memory only and may need to be re-applied after future restarts.

#### SSH key setup (the gotcha)

RunPod offers two SSH forms and they use different keys:

1. **`ssh.runpod.io` proxy** — picks up keys from RunPod **account settings**. Enough for shell access.
2. **Direct TCP form** (`ssh root@<host> -p <port>`) — picks up keys from `/root/.ssh/authorized_keys` **inside the pod**. This is the form that supports `ssh -L` port forwarding.

To get a local browser onto the pod via tunnel, the public key must be in **both** places. Once both are set:

```
ssh -i ~/.ssh/id_ed25519 -L 8000:127.0.0.1:8000 root@<host> -p <port>
```

Then visit `http://127.0.0.1:8000/` locally.

Stop with `tmux kill-session -t drone`.

## 7. Useful pointers

- `app/mavlink_link.py` — MAVLink ↔ asyncio bridge; reader thread + `call_soon_threadsafe`, two `mavutil.mavlink_connection`s.
- `app/telemetry_bus.py` — pub/sub bus, per-`system_id` `DroneState`, 500 ms batched DB flush, `ARDUPILOT_MODE_BY_INT` map.
- `app/command_service.py` — `COMMAND_LONG` issuance and `COMMAND_ACK` correlation via `pending` future map; `goto` shortcut.
- `app/main.py` — FastAPI app factory, lifespan wiring, static dashboard mount, `/api/config` endpoint.
- `app/static/app.js` — dashboard client: fetches `/api/config`, loads Google Maps SDK, runs WebSocket subscriber, view/tilt/goto controls.
- `mock_drone/sim.py` — deterministic state machine, pure `tick(dt)`; the file unit tests exercise.
- `RUNPOD_INSTRUCTIONS.txt` — canonical pod runbook (image, env, tmux, smoke test).
- `.env.example` — every supported env var.
- `docs/MAP_GUIDE.md` — end-user walkthrough of the dashboard, Pegman, Tilt 3D, goto.

## 8. Deferred / out of scope

- ALFA dataset replay (CSV-based, no ROS) — v1 deliberately excludes; service preserves an entry point for a future `app/alfa_replay.py` that pushes synthetic frames through `bus.ingest`.
- Server-GPU ML anomaly detection (v2) — documented in `RUNPOD_INSTRUCTIONS.txt` and the plan file; not in v1.
- Three.js 3D drone overlay (Level 2 / `TODO.txt` #9) — replace flat marker with a WebGLOverlayView model rotated by roll/pitch/yaw and altitude in 3D space.
- deck.gl trail (Level 3 / `TODO.txt` #10) — replace the `google.maps.Polyline` trail with a `PathLayer`/`ArcLayer`, altitude as 3D ribbon, speed as color.
- Photorealistic 3D Tiles upgrade for the basemap.
- Multi-drone (`TODO.txt` #5) — bus already keys on `system_id`, but the dashboard panel and command routes assume a single drone.
- Google Maps API key restriction (HTTP referrer / API restriction in Cloud Console) — currently the key is served openly via `/api/config` to any browser hitting the dashboard.
- Latency dashboard (`TODO.txt` #6), moving obstacles (`TODO.txt` #7), Street-Live-View autonomous navigation with CUA + LLM (`TODO.txt` #3, #4, #8), Nemoclaw autonomous deploy (`TODO.txt` #2), building-as-obstacle map cleanup (`TODO.txt` #1).
- Rust backend latency benchmark (`TODO.txt` #11) — split-screen dashboard with the current FastAPI (Python) on the left and a Rust backend (axum + tokio + mavlink crate) on the right; both subscribe to the same mock drone (multi-target UDP), each fans out telemetry on its own port (8000 / 9000) with its own `google.maps.Map` and WebSocket; t_ingest / t_emit / t_recv timestamps drive p50 + p99 badges per pane (backend processing, end-to-end, jitter). Scope: telemetry + commands, no DB on the Rust side; deploy on RunPod with both ports exposed.

## 9. Recent additions (post-Level-1)

Captured during the second half of the 2026-05-09 session:

- **Public dashboard URL.** Pod now exposes `8000` via RunPod's HTTP proxy (alongside `8888` for Jupyter); `https://<pod-id>-8000.proxy.runpod.net` is reachable from any browser without an SSH tunnel. No auth on the dashboard — anyone with the URL can issue commands. Fine for CUA experiments, not production. (See **Deployment story → Public dashboard URL**.)
- **Pod-restart DNS gotcha.** After a stop/start, `/etc/resolv.conf` was set to `nameserver 127.0.0.11` (Docker's internal resolver) and external DNS broke. Workaround is to write `nameserver 8.8.8.8` / `1.1.1.1` into `/etc/resolv.conf`; it's in-memory only and may recur. (See **Deployment story → Pod-restart DNS gotcha**.)
- **Pod-restart recovery sequence.** `/workspace` survives but processes don't. Re-install tmux, re-activate venv, run `alembic upgrade head`, re-create the tmux session per `RUNPOD_INSTRUCTIONS.txt` step 6. (See **Deployment story → Pod-restart recovery**.)
- **CLAUDE.md location decision.** `drone_management/CLAUDE.md` stays where it is (deep, drone-specific). No top-level `Northstar/CLAUDE.md` is being added — the parent repo also contains unrelated CUA / Lightcone work, and we don't want to mix project guidance.
- **`docs/MAP_GUIDE.md` added.** Kid-friendly walkthrough of the dashboard (Pegman, Tilt 3D, goto, what the numbers mean) for non-technical users. Already linked from **Useful pointers**.
- **TODO additions captured.** `TODO.txt` now includes #9 (Three.js 3D drone overlay via WebGLOverlayView), #10 (deck.gl trail layer), and #11 (Python-vs-Rust split-screen latency benchmark on RunPod). All three tracked in **Deferred / out of scope**.
