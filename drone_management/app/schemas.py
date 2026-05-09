from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DroneOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    system_id: int
    component_id: int
    name: str
    last_heartbeat_at: datetime | None
    online: bool = False


class TelemetryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    drone_id: int
    ts: datetime
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


class CommandOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    drone_id: int
    kind: str
    params_json: str
    sent_at: datetime
    ack_status: str | None
    ack_at: datetime | None


class TakeoffBody(BaseModel):
    alt_m: float = Field(gt=0, le=500)


class GotoBody(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    alt_m: float = Field(gt=0, le=500)


class ModeBody(BaseModel):
    mode: Literal["MANUAL", "AUTO", "RTL"]


class CommandResult(BaseModel):
    command_id: int
    status: str
