"""Local viewer dashboard for the CUA loop.

Exposes a FastAPI app served by uvicorn in a daemon thread. The CUA loop calls
`publish(event)` from the main thread; events cross into the asyncio world via
a `queue.Queue` and fan out to WebSocket subscribers.
"""
from __future__ import annotations

import asyncio
import queue
import socket
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


STATIC_DIR = Path(__file__).resolve().parent / "static"

_event_queue: queue.Queue = queue.Queue()
_subscribers: list[asyncio.Queue] = []
_history: list[dict] = []
_history_cap: int = 200

app = FastAPI(title="cua-dashboard")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()
    q: asyncio.Queue = asyncio.Queue(maxsize=512)
    _subscribers.append(q)
    try:
        for past in _history:
            await websocket.send_json(past)
        while True:
            event = await q.get()
            await websocket.send_json(event)
    except WebSocketDisconnect:
        pass
    finally:
        if q in _subscribers:
            _subscribers.remove(q)


async def _drain_loop():
    loop = asyncio.get_running_loop()
    while True:
        try:
            event = await loop.run_in_executor(None, _event_queue.get, True, 1.0)
        except queue.Empty:
            continue
        if event is None:
            continue
        _history.append(event)
        if len(_history) > _history_cap:
            del _history[: len(_history) - _history_cap]
        dead = []
        for q_sub in _subscribers:
            try:
                q_sub.put_nowait(event)
            except asyncio.QueueFull:
                dead.append(q_sub)
        for d in dead:
            if d in _subscribers:
                _subscribers.remove(d)


@app.on_event("startup")
async def _on_startup():
    asyncio.create_task(_drain_loop())


def publish(event: dict) -> None:
    """Thread-safe push from any thread (sync). The asyncio drainer fans out."""
    try:
        _event_queue.put_nowait(event)
    except queue.Full:
        pass


def _port_is_open(port: int, host: str = "127.0.0.1", timeout: float = 0.2) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        try:
            s.connect((host, port))
            return True
        except OSError:
            return False


def _wait_until_ready(port: int, deadline_s: float = 3.0) -> bool:
    end = time.monotonic() + deadline_s
    while time.monotonic() < end:
        if _port_is_open(port):
            return True
        time.sleep(0.05)
    return False


def start_server(port: int = 9090, host: str = "127.0.0.1", open_browser: bool = True) -> None:
    """Run uvicorn in a daemon thread. Returns once the port is reachable."""
    config = uvicorn.Config(app, host=host, port=port, log_level="warning", access_log=False)
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="cua-dashboard", daemon=True)
    thread.start()
    if not _wait_until_ready(port):
        raise RuntimeError(f"cua dashboard server didn't bind {host}:{port} in time")
    url = f"http://localhost:{port}"
    print(f"[dashboard] live at {url}")
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception as e:
            print(f"[dashboard] could not auto-open browser: {e}")
