from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from . import db as _db
from .mavlink_link import ParsedMessage
from .models import Drone, TelemetryRecord


# ArduPilot custom_mode → human label
ARDUPILOT_MODE_BY_INT = {0: "MANUAL", 10: "AUTO", 6: "RTL"}


@dataclass
class DroneState:
    """Latest known state for a drone, accumulated from streaming MAVLink frames."""
    system_id: int
    component_id: int
    drone_id: int | None = None
    last_heartbeat_at: datetime | None = None
    lat: float | None = None
    lon: float | None = None
    alt_m: float | None = None
    rel_alt_m: float | None = None
    heading_deg: float | None = None
    vx: float | None = None
    vy: float | None = None
    vz: float | None = None
    roll: float | None = None
    pitch: float | None = None
    yaw: float | None = None
    battery_voltage: float | None = None
    battery_remaining: int | None = None
    gps_fix_type: int | None = None
    satellites: int | None = None
    mode: str | None = None
    armed: bool | None = None

    def as_payload(self) -> dict[str, Any]:
        return {
            "system_id": self.system_id,
            "drone_id": self.drone_id,
            "lat": self.lat,
            "lon": self.lon,
            "alt_m": self.alt_m,
            "rel_alt_m": self.rel_alt_m,
            "heading_deg": self.heading_deg,
            "vx": self.vx, "vy": self.vy, "vz": self.vz,
            "roll": self.roll, "pitch": self.pitch, "yaw": self.yaw,
            "battery_voltage": self.battery_voltage,
            "battery_remaining": self.battery_remaining,
            "gps_fix_type": self.gps_fix_type,
            "satellites": self.satellites,
            "mode": self.mode,
            "armed": self.armed,
            "last_heartbeat_at": self.last_heartbeat_at.isoformat() if self.last_heartbeat_at else None,
        }


@dataclass
class TelemetryBus:
    """In-process pub/sub fan-out + buffered DB writer.

    Thread-safe entry point: `ingest()` is called from the event loop after the MAVLink
    reader thread hands a message via `loop.call_soon_threadsafe`. We never await DB
    writes from the WS fan-out path; a dedicated flusher coroutine batches inserts.
    """
    states: dict[int, DroneState] = field(default_factory=dict)
    subscribers: set[asyncio.Queue] = field(default_factory=set)
    buffer: list[dict[str, Any]] = field(default_factory=list)
    buffer_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    flush_interval_s: float = 0.5
    _flusher_task: asyncio.Task | None = None

    async def start(self) -> None:
        await self._sync_drones_from_db()
        self._flusher_task = asyncio.create_task(self._flush_loop(), name="telemetry-flusher")

    async def stop(self) -> None:
        if self._flusher_task:
            self._flusher_task.cancel()
            try:
                await self._flusher_task
            except (asyncio.CancelledError, Exception):
                pass
        await self._flush_buffer()

    async def _sync_drones_from_db(self) -> None:
        async with _db.SessionLocal() as s:
            rows = (await s.execute(select(Drone))).scalars().all()
            for d in rows:
                state = self.states.setdefault(d.system_id, DroneState(d.system_id, d.component_id))
                state.drone_id = d.id
                state.component_id = d.component_id
                state.last_heartbeat_at = d.last_heartbeat_at

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=1024)
        self.subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self.subscribers.discard(q)

    def broadcast(self, payload: dict[str, Any]) -> None:
        dead: list[asyncio.Queue] = []
        for q in self.subscribers:
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            self.subscribers.discard(q)

    def ingest(self, msg: ParsedMessage) -> None:
        """Called from the event loop with a parsed MAVLink message."""
        # Skip messages from the GCS itself (some pymavlink loopback configs).
        if msg.sender_system == 0:
            return

        state = self.states.setdefault(
            msg.sender_system, DroneState(msg.sender_system, msg.sender_component),
        )
        state.component_id = msg.sender_component
        p = msg.payload

        if msg.msg_type == "HEARTBEAT":
            state.last_heartbeat_at = datetime.now(timezone.utc)
            state.armed = bool(p.get("base_mode", 0) & 0b1000_0000)
            state.mode = ARDUPILOT_MODE_BY_INT.get(p.get("custom_mode", -1), state.mode)
        elif msg.msg_type == "GLOBAL_POSITION_INT":
            state.lat = p["lat"] / 1e7
            state.lon = p["lon"] / 1e7
            state.alt_m = p["alt"] / 1000.0
            state.rel_alt_m = p["relative_alt"] / 1000.0
            state.vx = p["vx"] / 100.0
            state.vy = p["vy"] / 100.0
            state.vz = p["vz"] / 100.0
            state.heading_deg = p["hdg"] / 100.0 if p.get("hdg", 65535) != 65535 else None
        elif msg.msg_type == "ATTITUDE":
            state.roll = p["roll"]
            state.pitch = p["pitch"]
            state.yaw = p["yaw"]
        elif msg.msg_type == "SYS_STATUS":
            state.battery_voltage = p["voltage_battery"] / 1000.0
            state.battery_remaining = p["battery_remaining"]
        elif msg.msg_type == "GPS_RAW_INT":
            state.gps_fix_type = p["fix_type"]
            state.satellites = p["satellites_visible"]

        ts = datetime.now(timezone.utc)

        self.broadcast({
            "type": "telemetry",
            "ts": ts.isoformat(),
            **state.as_payload(),
        })

        # Persist a row per HEARTBEAT to keep DB volume manageable
        # (telemetry stream still goes out at full rate to WS subscribers).
        if msg.msg_type == "HEARTBEAT":
            self.buffer.append({
                "system_id": state.system_id,
                "component_id": state.component_id,
                "ts": ts,
                **{k: getattr(state, k) for k in (
                    "lat", "lon", "alt_m", "rel_alt_m", "heading_deg",
                    "vx", "vy", "vz",
                    "roll", "pitch", "yaw",
                    "battery_voltage", "battery_remaining",
                    "gps_fix_type", "satellites",
                    "mode", "armed",
                )},
            })

    async def _flush_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(self.flush_interval_s)
                await self._flush_buffer()
        except asyncio.CancelledError:
            return

    async def _flush_buffer(self) -> None:
        if not self.buffer:
            return
        async with self.buffer_lock:
            pending, self.buffer = self.buffer, []
        if not pending:
            return
        async with _db.SessionLocal() as s:
            for row in pending:
                state = self.states.get(row["system_id"])
                if state is None:
                    continue
                if state.drone_id is None:
                    drone = (await s.execute(
                        select(Drone).where(Drone.system_id == row["system_id"])
                    )).scalar_one_or_none()
                    if drone is None:
                        drone = Drone(
                            system_id=row["system_id"],
                            component_id=row["component_id"],
                            name=f"drone-{row['system_id']}",
                            last_heartbeat_at=row["ts"],
                        )
                        s.add(drone)
                        await s.flush()
                    state.drone_id = drone.id
                    state.last_heartbeat_at = row["ts"]
                else:
                    await s.execute(
                        Drone.__table__.update()
                        .where(Drone.id == state.drone_id)
                        .values(last_heartbeat_at=row["ts"])
                    )
                s.add(TelemetryRecord(
                    drone_id=state.drone_id,
                    ts=row["ts"],
                    lat=row["lat"], lon=row["lon"], alt_m=row["alt_m"],
                    rel_alt_m=row["rel_alt_m"], heading_deg=row["heading_deg"],
                    vx=row["vx"], vy=row["vy"], vz=row["vz"],
                    roll=row["roll"], pitch=row["pitch"], yaw=row["yaw"],
                    battery_voltage=row["battery_voltage"],
                    battery_remaining=row["battery_remaining"],
                    gps_fix_type=row["gps_fix_type"], satellites=row["satellites"],
                    mode=row["mode"], armed=row["armed"],
                ))
            await s.commit()


bus = TelemetryBus()


async def stream_for_subscriber(q: asyncio.Queue) -> AsyncIterator[str]:
    try:
        while True:
            payload = await q.get()
            yield json.dumps(payload, default=str)
    finally:
        bus.unsubscribe(q)
