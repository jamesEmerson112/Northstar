"""CLI: python -m cua "<goal>"   (run from drone_management/)

Runs a Northstar CUA loop against the public drone dashboard.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from . import runner
from .config import dashboard_url, load_lightcone_api_key
from .tasks import ALL as DEMO_TASKS


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a Northstar CUA task on the drone dashboard.")
    parser.add_argument(
        "goal",
        nargs="?",
        help="Natural-language task. If omitted, use --demo.",
    )
    parser.add_argument(
        "--demo",
        choices=sorted(DEMO_TASKS.keys()),
        help="Run a pre-canned demo task instead of typing a goal.",
    )
    parser.add_argument(
        "--dashboard-url",
        default=dashboard_url(),
        help="Public dashboard URL to drive (default: %(default)s).",
    )
    parser.add_argument("--max-steps", type=int, default=30)
    parser.add_argument(
        "--output-dir",
        default="cua_runs",
        help="Where to write annotated PNGs (default: %(default)s/<timestamp>/).",
    )
    args = parser.parse_args(argv)

    if not args.goal and not args.demo:
        parser.error("either GOAL or --demo is required")
    if args.goal and args.demo:
        parser.error("pass GOAL or --demo, not both")

    goal = args.goal if args.goal else DEMO_TASKS[args.demo]

    try:
        api_key = load_lightcone_api_key()
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    out = Path(args.output_dir) / datetime.now().strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=True)

    runner.run(
        goal=goal,
        dashboard_url=args.dashboard_url,
        lightcone_api_key=api_key,
        output_dir=out,
        max_steps=args.max_steps,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
