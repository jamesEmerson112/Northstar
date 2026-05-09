from __future__ import annotations

import httpx


class Streamer:
    """POSTs CUA step events to /api/cua/step on the public dashboard.

    Streaming failure never raises — the CUA loop must keep running even if
    the dashboard is unreachable. Local PNGs are still saved as backup.
    """

    def __init__(self, dashboard_url: str, run_id: str):
        self.url = dashboard_url.rstrip("/") + "/api/cua/step"
        self.run_id = run_id
        self.client = httpx.Client(timeout=5.0)

    def send_start(self, task: str) -> None:
        self._post({"status": "start", "step": 0, "task": task})

    def send_step(self, step: int, action_label: str, screenshot_b64: str | None) -> None:
        self._post({
            "status": "step",
            "step": step,
            "action_label": action_label,
            "screenshot_b64": screenshot_b64,
        })

    def send_done(self) -> None:
        self._post({"status": "done", "step": -1})

    def send_error(self, msg: str) -> None:
        self._post({"status": "error", "step": -1, "error": msg})

    def _post(self, payload: dict) -> None:
        body = {"run_id": self.run_id, **{k: v for k, v in payload.items() if v is not None}}
        try:
            self.client.post(self.url, json=body)
        except Exception as e:
            print(f"[streamer] non-fatal post failure: {e}")

    def close(self) -> None:
        try:
            self.client.close()
        except Exception:
            pass
