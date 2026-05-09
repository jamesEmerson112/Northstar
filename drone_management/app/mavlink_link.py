from __future__ import annotations

import asyncio
import os
import threading
from dataclasses import dataclass, field
from typing import Any, Callable

os.environ.setdefault("MAVLINK20", "1")
os.environ.setdefault("MAVLINK_DIALECT", "ardupilotmega")

from pymavlink import mavutil  # noqa: E402  must come after env setup


@dataclass
class ParsedMessage:
    msg_type: str
    sender_system: int
    sender_component: int
    payload: dict[str, Any]


@dataclass
class MavlinkLink:
    bind_host: str
    bind_port: int
    drone_host: str
    drone_port: int
    gcs_system_id: int = 255
    gcs_component_id: int = 190
    on_message: Callable[[ParsedMessage], None] | None = None
    _conn: Any = field(default=None, init=False)
    _send_conn: Any = field(default=None, init=False)
    _thread: threading.Thread | None = field(default=None, init=False)
    _loop: asyncio.AbstractEventLoop | None = field(default=None, init=False)
    _stop: threading.Event = field(default_factory=threading.Event, init=False)
    _send_lock: threading.Lock = field(default_factory=threading.Lock, init=False)

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        # Inbound: bind UDP socket to listen for telemetry from drones.
        self._conn = mavutil.mavlink_connection(
            f"udpin:{self.bind_host}:{self.bind_port}",
            source_system=self.gcs_system_id,
            source_component=self.gcs_component_id,
            dialect="ardupilotmega",
        )
        # Outbound: separate connection that sends commands to the drone.
        self._send_conn = mavutil.mavlink_connection(
            f"udpout:{self.drone_host}:{self.drone_port}",
            source_system=self.gcs_system_id,
            source_component=self.gcs_component_id,
            dialect="ardupilotmega",
        )
        self._stop.clear()
        self._thread = threading.Thread(target=self._reader_loop, name="mavlink-reader", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        for conn in (self._conn, self._send_conn):
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    def _reader_loop(self) -> None:
        assert self._conn is not None
        while not self._stop.is_set():
            try:
                msg = self._conn.recv_match(blocking=True, timeout=1.0)
            except Exception:
                continue
            if msg is None or msg.get_type() == "BAD_DATA":
                continue
            parsed = ParsedMessage(
                msg_type=msg.get_type(),
                sender_system=msg.get_srcSystem(),
                sender_component=msg.get_srcComponent(),
                payload=msg.to_dict(),
            )
            if self._loop is not None and self.on_message is not None:
                cb = self.on_message
                self._loop.call_soon_threadsafe(cb, parsed)

    def _send_blocking(self, fn: Callable[[Any], None]) -> None:
        with self._send_lock:
            fn(self._send_conn.mav)

    async def send(self, fn: Callable[[Any], None]) -> None:
        await asyncio.to_thread(self._send_blocking, fn)
