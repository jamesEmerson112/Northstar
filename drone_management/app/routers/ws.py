import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..telemetry_bus import bus


router = APIRouter()


@router.websocket("/ws/telemetry")
async def ws_telemetry(websocket: WebSocket):
    await websocket.accept()
    q = bus.subscribe()
    try:
        # Send a snapshot of current state on connect.
        for state in bus.states.values():
            await websocket.send_text(json.dumps({
                "type": "snapshot",
                **state.as_payload(),
            }, default=str))

        while True:
            payload = await q.get()
            await websocket.send_text(json.dumps(payload, default=str))
    except WebSocketDisconnect:
        pass
    finally:
        bus.unsubscribe(q)
