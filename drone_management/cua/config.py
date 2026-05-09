from __future__ import annotations

import os
from pathlib import Path


DEFAULT_DASHBOARD_URL = "https://un5nmdhn7f29dw-8000.proxy.runpod.net"


def load_lightcone_api_key() -> str:
    key = os.getenv("LIGHTCONE_API_KEY") or os.getenv("lightcone_API")
    if key:
        return key
    for candidate in (
        Path.cwd() / ".env",
        Path(__file__).resolve().parent.parent / ".env",
        Path(__file__).resolve().parent.parent.parent / ".env",
    ):
        if not candidate.is_file():
            continue
        for line in candidate.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k in ("LIGHTCONE_API_KEY", "lightcone_API") and v:
                return v
    raise RuntimeError(
        "LIGHTCONE_API_KEY not set. Add it to your shell env or ~/Northstar/.env."
    )


def dashboard_url() -> str:
    return os.getenv("DASHBOARD_URL", DEFAULT_DASHBOARD_URL).rstrip("/")
