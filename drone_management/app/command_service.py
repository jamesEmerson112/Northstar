from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from pymavlink import mavutil

from . import db as _db
from .mavlink_link import MavlinkLink, ParsedMessage
from .models import Command


ACK_RESULT_NAMES = {
    0: "ACCEPTED",
    1: "TEMPORARILY_REJECTED",
    2: "DENIED",
    3: "UNSUPPORTED",
    4: "FAILED",
    5: "IN_PROGRESS",
    6: "CANCELLED",
}


@dataclass
class CommandService:
    link: MavlinkLink
    pending: dict[int, asyncio.Future] = field(default_factory=dict)
    ack_timeout_s: float = 3.0

    def handle_message(self, msg: ParsedMessage) -> None:
        if msg.msg_type != "COMMAND_ACK":
            return
        cmd_id = int(msg.payload.get("command", -1))
        result = int(msg.payload.get("result", 4))
        fut = self.pending.pop(cmd_id, None)
        if fut and not fut.done():
            fut.set_result(ACK_RESULT_NAMES.get(result, f"RESULT_{result}"))

    async def _await_ack(self, mav_cmd_id: int) -> str:
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        # If we get a duplicate cmd id mid-flight, prefer the latest waiter.
        prev = self.pending.get(mav_cmd_id)
        if prev and not prev.done():
            prev.cancel()
        self.pending[mav_cmd_id] = fut
        try:
            return await asyncio.wait_for(fut, timeout=self.ack_timeout_s)
        except asyncio.TimeoutError:
            self.pending.pop(mav_cmd_id, None)
            return "TIMEOUT"

    async def _log(self, drone_id: int, kind: str, params: dict[str, Any]) -> int:
        async with _db.SessionLocal() as s:
            row = Command(
                drone_id=drone_id,
                kind=kind,
                params_json=json.dumps(params),
                ack_status="PENDING",
            )
            s.add(row)
            await s.commit()
            await s.refresh(row)
            return row.id

    async def _finalize(self, command_id: int, status: str) -> None:
        async with _db.SessionLocal() as s:
            await s.execute(
                Command.__table__.update()
                .where(Command.id == command_id)
                .values(ack_status=status, ack_at=datetime.now(timezone.utc))
            )
            await s.commit()

    async def _send_command_long(
        self,
        target_system: int,
        target_component: int,
        mav_cmd: int,
        params: tuple[float, float, float, float, float, float, float],
    ) -> str:
        await self.link.send(lambda mav: mav.command_long_send(
            target_system, target_component, mav_cmd, 0, *params,
        ))
        return await self._await_ack(mav_cmd)

    async def arm(self, drone_id: int, target_system: int, target_component: int, *, armed: bool) -> tuple[int, str]:
        cmd_id = await self._log(drone_id, "arm" if armed else "disarm", {})
        status = await self._send_command_long(
            target_system, target_component,
            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
            (1.0 if armed else 0.0, 0, 0, 0, 0, 0, 0),
        )
        await self._finalize(cmd_id, status)
        return cmd_id, status

    async def takeoff(self, drone_id: int, target_system: int, target_component: int, *, alt_m: float) -> tuple[int, str]:
        cmd_id = await self._log(drone_id, "takeoff", {"alt_m": alt_m})
        status = await self._send_command_long(
            target_system, target_component,
            mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
            (0, 0, 0, 0, 0, 0, alt_m),
        )
        await self._finalize(cmd_id, status)
        return cmd_id, status

    async def land(self, drone_id: int, target_system: int, target_component: int) -> tuple[int, str]:
        cmd_id = await self._log(drone_id, "land", {})
        status = await self._send_command_long(
            target_system, target_component,
            mavutil.mavlink.MAV_CMD_NAV_LAND,
            (0, 0, 0, 0, 0, 0, 0),
        )
        await self._finalize(cmd_id, status)
        return cmd_id, status

    async def set_mode(self, drone_id: int, target_system: int, target_component: int, *, mode: str) -> tuple[int, str]:
        # ArduPilot custom_mode mapping
        mode_map = {"MANUAL": 0, "AUTO": 10, "RTL": 6}
        custom = mode_map[mode]
        base = mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED
        cmd_id = await self._log(drone_id, "set_mode", {"mode": mode})
        status = await self._send_command_long(
            target_system, target_component,
            mavutil.mavlink.MAV_CMD_DO_SET_MODE,
            (float(base), float(custom), 0, 0, 0, 0, 0),
        )
        await self._finalize(cmd_id, status)
        return cmd_id, status

    async def goto(
        self,
        drone_id: int,
        target_system: int,
        target_component: int,
        *,
        lat: float, lon: float, alt_m: float,
    ) -> tuple[int, str]:
        cmd_id = await self._log(drone_id, "goto", {"lat": lat, "lon": lon, "alt_m": alt_m})

        # SET_POSITION_TARGET_GLOBAL_INT — position-only mask
        type_mask = 0b0000_1111_1111_1000

        await self.link.send(lambda mav: mav.set_position_target_global_int_send(
            0,                              # time_boot_ms (ignored)
            target_system, target_component,
            mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
            type_mask,
            int(lat * 1e7), int(lon * 1e7), float(alt_m),
            0, 0, 0,                        # vx, vy, vz
            0, 0, 0,                        # afx, afy, afz
            0, 0,                           # yaw, yaw_rate
        ))

        # No COMMAND_ACK for SET_POSITION_TARGET_GLOBAL_INT in MAVLink; treat as accepted on send.
        await self._finalize(cmd_id, "ACCEPTED")
        return cmd_id, "ACCEPTED"


cmd_service: CommandService | None = None
