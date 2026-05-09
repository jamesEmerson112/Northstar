from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from typing import Any

os.environ.setdefault("MAVLINK20", "1")
os.environ.setdefault("MAVLINK_DIALECT", "ardupilotmega")

from pymavlink import mavutil  # noqa: E402


@dataclass
class MockMavIO:
    """Pair of pymavlink connections for the mock drone:
    - `out`: udpout to the GCS (service) for telemetry.
    - `inp`: udpin where we listen for commands from the GCS.
    """
    target_host: str
    target_port: int
    listen_host: str
    listen_port: int
    system_id: int = 1
    component_id: int = 1
    out: Any = None
    inp: Any = None
    _send_lock: threading.Lock = field(default_factory=threading.Lock)

    def open(self) -> None:
        self.out = mavutil.mavlink_connection(
            f"udpout:{self.target_host}:{self.target_port}",
            source_system=self.system_id,
            source_component=self.component_id,
            dialect="ardupilotmega",
        )
        self.inp = mavutil.mavlink_connection(
            f"udpin:{self.listen_host}:{self.listen_port}",
            source_system=self.system_id,
            source_component=self.component_id,
            dialect="ardupilotmega",
        )

    def close(self) -> None:
        for conn in (self.out, self.inp):
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    def recv(self, timeout: float = 0.0):
        if self.inp is None:
            return None
        return self.inp.recv_match(blocking=timeout > 0, timeout=timeout)

    def send_heartbeat(self) -> None:
        with self._send_lock:
            self.out.mav.heartbeat_send(
                mavutil.mavlink.MAV_TYPE_FIXED_WING,
                mavutil.mavlink.MAV_AUTOPILOT_ARDUPILOTMEGA,
                0, 0, 0,
            )

    def send_state(self, *, base_mode: int, custom_mode: int) -> None:
        with self._send_lock:
            self.out.mav.heartbeat_send(
                mavutil.mavlink.MAV_TYPE_FIXED_WING,
                mavutil.mavlink.MAV_AUTOPILOT_ARDUPILOTMEGA,
                base_mode, custom_mode,
                mavutil.mavlink.MAV_STATE_ACTIVE,
            )

    def send_global_position(self, *, time_boot_ms: int, lat: float, lon: float, alt_m: float, rel_alt_m: float, hdg_deg: float) -> None:
        with self._send_lock:
            self.out.mav.global_position_int_send(
                time_boot_ms,
                int(lat * 1e7), int(lon * 1e7),
                int(alt_m * 1000), int(rel_alt_m * 1000),
                0, 0, 0,
                int(hdg_deg * 100) if hdg_deg is not None else 65535,
            )

    def send_attitude(self, *, time_boot_ms: int, roll: float, pitch: float, yaw: float) -> None:
        with self._send_lock:
            self.out.mav.attitude_send(time_boot_ms, roll, pitch, yaw, 0.0, 0.0, 0.0)

    def send_sys_status(self, *, voltage_v: float, battery_pct: int) -> None:
        with self._send_lock:
            self.out.mav.sys_status_send(
                0, 0, 0,                    # sensors
                500,                        # load (cdeg)
                int(voltage_v * 1000),      # voltage_battery (mV)
                -1, battery_pct,            # current_battery (-1=unknown), battery_remaining %
                0, 0, 0, 0, 0, 0,
            )

    def send_gps_raw_int(self, *, time_usec: int, lat: float, lon: float, alt_m: float) -> None:
        with self._send_lock:
            self.out.mav.gps_raw_int_send(
                time_usec,
                3,                          # 3D fix
                int(lat * 1e7), int(lon * 1e7), int(alt_m * 1000),
                65535, 65535, 0, 0, 12,     # eph, epv, vel, cog, satellites_visible
            )

    def send_command_ack(self, command: int, result: int) -> None:
        with self._send_lock:
            self.out.mav.command_ack_send(command, result)
