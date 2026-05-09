from fastapi import APIRouter, HTTPException

from ..schemas import CuaStepBody
from ..telemetry_bus import bus


router = APIRouter(prefix="/api/cua", tags=["cua"])


@router.post("/step")
async def cua_step(body: CuaStepBody):
    bus.broadcast({"type": "cua_step", **body.model_dump(exclude_none=True)})
    return {"ok": True}


@router.post("/run")
async def cua_run():
    raise HTTPException(status_code=501, detail="CLI-only in v0; run `python -m cua` from drone_management/")
