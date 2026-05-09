# drone_management

Bidirectional drone telemetry + management service (v1). Mock drone speaks MAVLink/UDP to a FastAPI service that persists to SQLite, fans out over WebSocket to a Leaflet dashboard, and sends commands back.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head

# Terminal 1
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Terminal 2
python -m mock_drone --target 127.0.0.1:14550 --listen 0.0.0.0:14551

# Browser
open http://localhost:8000/
```

## Commands

| Endpoint | Body |
|---|---|
| `POST /api/drones/{id}/commands/arm` | `{}` |
| `POST /api/drones/{id}/commands/disarm` | `{}` |
| `POST /api/drones/{id}/commands/takeoff` | `{"alt_m": 20}` |
| `POST /api/drones/{id}/commands/land` | `{}` |
| `POST /api/drones/{id}/commands/goto` | `{"lat": 37.78, "lon": -122.42, "alt_m": 20}` |
| `POST /api/drones/{id}/commands/mode` | `{"mode": "AUTO"}` |

WebSocket stream: `ws://localhost:8000/ws/telemetry`.

ArduPilot custom mode integers used in v1: `MANUAL=0`, `AUTO=10`, `RTL=6`. Adjust if targeting PX4.

## Configuration

| Env var | Default | Notes |
|---|---|---|
| `DB_URL` | `sqlite+aiosqlite:///./drone_management.db` | Switch to `/workspace/...` on RunPod |
| `MAVLINK_BIND_HOST` | `0.0.0.0` | UDP listen host (service ingest) |
| `MAVLINK_BIND_PORT` | `14550` | UDP listen port |
| `DRONE_HOST` | `127.0.0.1` | Mock drone host (where service sends commands) |
| `DRONE_PORT` | `14551` | Mock drone command-listen port |
| `HTTP_HOST` | `127.0.0.1` | uvicorn bind |
| `HTTP_PORT` | `8000` | uvicorn port |
