from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import command_service as cs_mod
from ..db import get_session
from ..models import Command, Drone
from ..schemas import CommandOut, CommandResult, GotoBody, ModeBody, TakeoffBody, TeleportBody


router = APIRouter(prefix="/api/drones/{drone_id}/commands", tags=["commands"])


async def _resolve_drone(drone_id: int, s: AsyncSession) -> Drone:
    drone = (await s.execute(select(Drone).where(Drone.id == drone_id))).scalar_one_or_none()
    if drone is None:
        raise HTTPException(status_code=404, detail="drone not found")
    return drone


def _service():
    if cs_mod.cmd_service is None:
        raise HTTPException(status_code=503, detail="MAVLink link not initialised")
    return cs_mod.cmd_service


@router.post("/arm", response_model=CommandResult)
async def cmd_arm(drone_id: int, s: AsyncSession = Depends(get_session)):
    drone = await _resolve_drone(drone_id, s)
    cid, status = await _service().arm(drone.id, drone.system_id, drone.component_id, armed=True)
    return CommandResult(command_id=cid, status=status)


@router.post("/disarm", response_model=CommandResult)
async def cmd_disarm(drone_id: int, s: AsyncSession = Depends(get_session)):
    drone = await _resolve_drone(drone_id, s)
    cid, status = await _service().arm(drone.id, drone.system_id, drone.component_id, armed=False)
    return CommandResult(command_id=cid, status=status)


@router.post("/takeoff", response_model=CommandResult)
async def cmd_takeoff(drone_id: int, body: TakeoffBody, s: AsyncSession = Depends(get_session)):
    drone = await _resolve_drone(drone_id, s)
    cid, status = await _service().takeoff(drone.id, drone.system_id, drone.component_id, alt_m=body.alt_m)
    return CommandResult(command_id=cid, status=status)


@router.post("/land", response_model=CommandResult)
async def cmd_land(drone_id: int, s: AsyncSession = Depends(get_session)):
    drone = await _resolve_drone(drone_id, s)
    cid, status = await _service().land(drone.id, drone.system_id, drone.component_id)
    return CommandResult(command_id=cid, status=status)


@router.post("/goto", response_model=CommandResult)
async def cmd_goto(drone_id: int, body: GotoBody, s: AsyncSession = Depends(get_session)):
    drone = await _resolve_drone(drone_id, s)
    cid, status = await _service().goto(
        drone.id, drone.system_id, drone.component_id,
        lat=body.lat, lon=body.lon, alt_m=body.alt_m,
    )
    return CommandResult(command_id=cid, status=status)


@router.post("/mode", response_model=CommandResult)
async def cmd_mode(drone_id: int, body: ModeBody, s: AsyncSession = Depends(get_session)):
    drone = await _resolve_drone(drone_id, s)
    cid, status = await _service().set_mode(drone.id, drone.system_id, drone.component_id, mode=body.mode)
    return CommandResult(command_id=cid, status=status)


@router.post("/teleport", response_model=CommandResult)
async def cmd_teleport(drone_id: int, body: TeleportBody, s: AsyncSession = Depends(get_session)):
    drone = await _resolve_drone(drone_id, s)
    cid, status = await _service().teleport(
        drone.id, drone.system_id, drone.component_id,
        lat=body.lat, lon=body.lon,
    )
    return CommandResult(command_id=cid, status=status)


@router.get("", response_model=list[CommandOut])
async def list_commands(
    drone_id: int,
    limit: int = Query(default=50, ge=1, le=500),
    s: AsyncSession = Depends(get_session),
):
    rows = (
        await s.execute(
            select(Command)
            .where(Command.drone_id == drone_id)
            .order_by(Command.sent_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return rows
