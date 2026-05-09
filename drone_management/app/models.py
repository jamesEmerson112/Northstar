from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Drone(Base):
    __tablename__ = "drones"

    id: Mapped[int] = mapped_column(primary_key=True)
    system_id: Mapped[int] = mapped_column(unique=True, index=True)
    component_id: Mapped[int]
    name: Mapped[str] = mapped_column(String(64), default="drone")
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    telemetry: Mapped[list["TelemetryRecord"]] = relationship(back_populates="drone")
    commands: Mapped[list["Command"]] = relationship(back_populates="drone")


class TelemetryRecord(Base):
    __tablename__ = "telemetry_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    drone_id: Mapped[int] = mapped_column(ForeignKey("drones.id"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    lat: Mapped[float | None]
    lon: Mapped[float | None]
    alt_m: Mapped[float | None]
    rel_alt_m: Mapped[float | None]
    heading_deg: Mapped[float | None]
    vx: Mapped[float | None]
    vy: Mapped[float | None]
    vz: Mapped[float | None]

    roll: Mapped[float | None]
    pitch: Mapped[float | None]
    yaw: Mapped[float | None]

    battery_voltage: Mapped[float | None]
    battery_remaining: Mapped[int | None]

    gps_fix_type: Mapped[int | None]
    satellites: Mapped[int | None]

    mode: Mapped[str | None] = mapped_column(String(32))
    armed: Mapped[bool | None]

    drone: Mapped[Drone] = relationship(back_populates="telemetry")


Index("ix_telemetry_drone_ts", TelemetryRecord.drone_id, TelemetryRecord.ts.desc())


class Command(Base):
    __tablename__ = "commands"

    id: Mapped[int] = mapped_column(primary_key=True)
    drone_id: Mapped[int] = mapped_column(ForeignKey("drones.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    params_json: Mapped[str] = mapped_column(default="{}")
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ack_status: Mapped[str | None] = mapped_column(String(16))
    ack_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    drone: Mapped[Drone] = relationship(back_populates="commands")
