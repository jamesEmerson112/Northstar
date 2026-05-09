from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import IntEnum


# ArduPilot custom_mode integers used in v1
class Mode(IntEnum):
    MANUAL = 0
    AUTO = 10
    RTL = 6


# Match the integer mapping the service uses (ARDUPILOT_MODE_BY_INT in telemetry_bus.py).
MODE_NAME = {Mode.MANUAL: "MANUAL", Mode.AUTO: "AUTO", Mode.RTL: "RTL"}


# Equirectangular conversion constants (small-area approximation)
EARTH_M_PER_DEG_LAT = 111_320.0


def m_per_deg_lon(lat_deg: float) -> float:
    return 111_320.0 * math.cos(math.radians(lat_deg))


@dataclass
class DroneSim:
    """Tiny non-physical drone state machine.

    All distances are meters, angles are degrees on the public surface.
    Updates are deterministic per `tick(dt)` call so tests can step it.
    """
    home_lat: float = 37.77927
    home_lon: float = -122.41924
    lat: float = field(init=False)
    lon: float = field(init=False)
    alt_m: float = 0.0
    rel_alt_m: float = 0.0
    target_lat: float | None = None
    target_lon: float | None = None
    target_alt_m: float | None = None
    armed: bool = False
    mode: Mode = Mode.MANUAL
    battery_pct_f: float = 100.0
    battery_v: float = 12.6
    yaw_deg: float = 0.0

    horiz_speed_m_s: float = 5.0
    vert_speed_m_s: float = 2.0
    last_command: str | None = None

    def __post_init__(self):
        self.lat = self.home_lat
        self.lon = self.home_lon

    # --- Command handlers -------------------------------------------------

    def cmd_arm(self, armed: bool) -> tuple[bool, str]:
        if not armed and self.rel_alt_m > 0.5:
            return False, "DENIED"
        self.armed = armed
        self.last_command = "arm" if armed else "disarm"
        return True, "ACCEPTED"

    def cmd_takeoff(self, alt_m: float) -> tuple[bool, str]:
        if not self.armed:
            return False, "DENIED"
        self.mode = Mode.AUTO
        self.target_alt_m = alt_m
        self.last_command = "takeoff"
        return True, "ACCEPTED"

    def cmd_land(self) -> tuple[bool, str]:
        self.target_alt_m = 0.0
        self.last_command = "land"
        return True, "ACCEPTED"

    def cmd_set_mode(self, mode: Mode) -> tuple[bool, str]:
        self.mode = mode
        self.last_command = f"set_mode:{MODE_NAME[mode]}"
        if mode == Mode.RTL:
            self.target_lat = self.home_lat
            self.target_lon = self.home_lon
            self.target_alt_m = 0.0
        return True, "ACCEPTED"

    def cmd_goto(self, lat: float, lon: float, alt_m: float) -> tuple[bool, str]:
        self.mode = Mode.AUTO
        self.target_lat = lat
        self.target_lon = lon
        self.target_alt_m = alt_m
        self.last_command = "goto"
        return True, "ACCEPTED"

    # --- Tick -------------------------------------------------------------

    def tick(self, dt: float) -> None:
        self._update_altitude(dt)
        self._update_horizontal(dt)
        self._update_battery(dt)
        if self.rel_alt_m <= 0.0 and self.target_alt_m == 0.0 and self.armed:
            # touchdown auto-disarm
            self.armed = False

    def _update_altitude(self, dt: float) -> None:
        if self.target_alt_m is None:
            return
        delta = self.target_alt_m - self.rel_alt_m
        step = self.vert_speed_m_s * dt
        if abs(delta) <= step:
            self.rel_alt_m = self.target_alt_m
        else:
            self.rel_alt_m += step if delta > 0 else -step
        if self.rel_alt_m < 0.0:
            self.rel_alt_m = 0.0
        self.alt_m = self.rel_alt_m  # treat home as 0 MSL for simplicity

    def _update_horizontal(self, dt: float) -> None:
        if self.target_lat is None or self.target_lon is None:
            return
        dy = (self.target_lat - self.lat) * EARTH_M_PER_DEG_LAT
        dx = (self.target_lon - self.lon) * m_per_deg_lon(self.lat)
        dist = math.hypot(dx, dy)
        if dist < 0.1:
            return
        step = self.horiz_speed_m_s * dt
        if step >= dist:
            self.lat = self.target_lat
            self.lon = self.target_lon
        else:
            self.lat += (dy / dist) * step / EARTH_M_PER_DEG_LAT
            self.lon += (dx / dist) * step / m_per_deg_lon(self.lat)
        self.yaw_deg = math.degrees(math.atan2(dx, dy)) % 360.0

    def _update_battery(self, dt: float) -> None:
        if self.armed and self.battery_pct_f > 0:
            # ~1% per minute drain when armed (cosmetic)
            self.battery_pct_f = max(0.0, self.battery_pct_f - dt / 60.0)
            self.battery_v = 11.1 + (self.battery_pct_f / 100.0) * 1.5

    @property
    def battery_pct(self) -> int:
        return int(self.battery_pct_f)
