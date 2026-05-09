from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import Drone, TelemetryRecord
from ..schemas import DroneOut, TelemetryOut


router = APIRouter(prefix="/api/drones", tags=["drones"])


def _is_online(last: datetime | None) -> bool:
    if last is None:
        return False
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - last) < timedelta(seconds=5)


@router.get("", response_model=list[DroneOut])
async def list_drones(s: AsyncSession = Depends(get_session)):
    rows = (await s.execute(select(Drone).order_by(Drone.id))).scalars().all()
    return [
        DroneOut(
            id=d.id, system_id=d.system_id, component_id=d.component_id,
            name=d.name, last_heartbeat_at=d.last_heartbeat_at,
            online=_is_online(d.last_heartbeat_at),
        )
        for d in rows
    ]


@router.get("/{drone_id}/telemetry/latest", response_model=TelemetryOut | None)
async def latest_telemetry(drone_id: int, s: AsyncSession = Depends(get_session)):
    row = (
        await s.execute(
            select(TelemetryRecord)
            .where(TelemetryRecord.drone_id == drone_id)
            .order_by(TelemetryRecord.ts.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return row


@router.get("/{drone_id}/telemetry", response_model=list[TelemetryOut])
async def telemetry_history(
    drone_id: int,
    since: datetime | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=5000),
    s: AsyncSession = Depends(get_session),
):
    drone = (
        await s.execute(select(Drone).where(Drone.id == drone_id))
    ).scalar_one_or_none()
    if drone is None:
        raise HTTPException(status_code=404, detail="drone not found")

    stmt = select(TelemetryRecord).where(TelemetryRecord.drone_id == drone_id)
    if since is not None:
        stmt = stmt.where(TelemetryRecord.ts >= since)
    stmt = stmt.order_by(TelemetryRecord.ts.desc()).limit(limit)
    rows = (await s.execute(stmt)).scalars().all()
    return rows
