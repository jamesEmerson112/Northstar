"""CLI: `python -m cua "<goal>"` (run from the Northstar/ directory).

Reads the Lightcone API key from $LIGHTCONE_API_KEY, $TZAFON_API_KEY, or the
legacy $lightcone_API. If none are set, falls back to reading Northstar/.env.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from . import dashboard, runner
from .tasks import ALL as DEMO_TASKS

DEFAULT_DASHBOARD_URL = "https://un5nmdhn7f29dw-8000.proxy.runpod.net"
NORTHSTAR_ROOT = Path(__file__).resolve().parent.parent


def _load_api_key_into_env() -> None:
    """Populate TZAFON_API_KEY from .env or legacy var so Lightcone() picks it up."""
    if os.environ.get("TZAFON_API_KEY"):
        return
    for alias in ("LIGHTCONE_API_KEY", "lightcone_API"):
        v = os.environ.get(alias)
        if v:
            os.environ["TZAFON_API_KEY"] = v
            return
    env_path = NORTHSTAR_ROOT / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key in ("TZAFON_API_KEY", "LIGHTCONE_API_KEY", "lightcone_API") and val:
            os.environ["TZAFON_API_KEY"] = val
            return


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a Northstar CUA task on the drone dashboard.")
    parser.add_argument("goal", nargs="?", help="natural-language task; omit when using --demo")
    parser.add_argument("--demo", choices=sorted(DEMO_TASKS.keys()),
                        help="run a pre-canned demo task")
    parser.add_argument("--dashboard-url",
                        default=os.getenv("DASHBOARD_URL", DEFAULT_DASHBOARD_URL).rstrip("/"))
    parser.add_argument("--max-steps", type=int, default=30)
    parser.add_argument("--output-dir", default=str(NORTHSTAR_ROOT / "cua_runs"))
    parser.add_argument("--port", type=int, default=9090,
                        help="local CUA viewer dashboard port (default 9090)")
    parser.add_argument("--no-open", action="store_true",
                        help="don't auto-open the browser")
    parser.add_argument("--no-dashboard", action="store_true",
                        help="skip the local viewer dashboard entirely")
    args = parser.parse_args(argv)

    if not args.goal and not args.demo:
        parser.error("either GOAL or --demo is required")
    if args.goal and args.demo:
        parser.error("pass GOAL or --demo, not both")

    goal = args.goal or DEMO_TASKS[args.demo]

    _load_api_key_into_env()
    if not os.environ.get("TZAFON_API_KEY"):
        print("error: no TZAFON_API_KEY found in env or Northstar/.env", file=sys.stderr)
        return 2

    out = Path(args.output_dir) / datetime.now().strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=True)

    if not args.no_dashboard:
        try:
            dashboard.start_server(port=args.port, open_browser=not args.no_open)
        except Exception as e:
            print(f"[main] could not start local dashboard: {e}", file=sys.stderr)

    try:
        runner.run(
            goal=goal,
            dashboard_url=args.dashboard_url,
            output_dir=out,
            max_steps=args.max_steps,
        )
    finally:
        if not args.no_dashboard:
            print(f"\n[main] CUA finished. Dashboard still live at http://localhost:{args.port}")
            print("[main] Press Ctrl-C to exit.")
            try:
                while True:
                    time.sleep(60)
            except KeyboardInterrupt:
                print("\n[main] bye.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
