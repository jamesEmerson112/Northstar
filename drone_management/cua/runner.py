"""CUA loop adapted for the drone_management dashboard.

Ported from Northstar/_cua.py + Northstar/visualize.py with two changes:
- annotated screenshots stream live to the FastAPI service (Streamer)
- screenshots also get persisted to a local cua_runs/ directory for review
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from tzafon import Lightcone
from tzafon.types.response_create_response import (
    OutputResponseComputerToolCall,
    OutputResponseFunctionToolCall,
    OutputResponseOutputMessage,
)

from .annotate import annotate_screenshot, save_image, to_base64_thumb
from .streamer import Streamer


DONE_TOOL = {
    "type": "function",
    "name": "done",
    "description": "Call this when the task is complete.",
    "parameters": {
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "Summary of what was accomplished."},
        },
    },
}

COORD_KEYS = {
    "x": "display_width", "x1": "display_width", "x2": "display_width",
    "y": "display_height", "y1": "display_height", "y2": "display_height",
}


def normalize_action(action, tool):
    d = action.model_dump() if hasattr(action, "model_dump") else dict(action)
    for key, dim in COORD_KEYS.items():
        if key in d and d[key] is not None:
            d[key] = int(d[key] / 1000 * tool[dim])
    if "keys" in d:
        keys = d["keys"]
        if isinstance(keys, str):
            d["keys"] = keys.split("+")
        elif isinstance(keys, list):
            flat = []
            for k in keys:
                try:
                    parsed = json.loads(k)
                    flat.extend(parsed if isinstance(parsed, list) else [parsed])
                except (json.JSONDecodeError, TypeError):
                    flat.append(k)
            d["keys"] = flat
    return d


def get_computer_calls(output, tool):
    calls, call_ids = [], []
    for item in output or []:
        if isinstance(item, OutputResponseComputerToolCall):
            calls.append(normalize_action(item.action, tool))
            call_ids.append(item.call_id)
        elif isinstance(item, dict) and item.get("type") == "computer_call":
            calls.append(normalize_action(item["action"], tool))
            call_ids.append(item["call_id"])
    return calls, call_ids


def is_done(output) -> bool:
    for item in output or []:
        if isinstance(item, OutputResponseFunctionToolCall) and item.name == "done":
            return True
        if isinstance(item, dict) and item.get("type") == "function_call" and item.get("name") == "done":
            return True
    return False


def get_messages(output) -> list[str]:
    texts: list[str] = []
    for item in output or []:
        if isinstance(item, OutputResponseOutputMessage):
            for block in item.content or []:
                if getattr(block, "text", None):
                    texts.append(block.text)
        elif isinstance(item, dict) and item.get("type") == "message":
            for block in item.get("content") or []:
                text = block.get("text") if isinstance(block, dict) else getattr(block, "text", None)
                if text:
                    texts.append(text)
    return texts


def format_action(d: dict) -> str:
    label = d.get("type", "?")
    if d.get("x") is not None:
        label += f" @ ({d['x']}, {d['y']})"
    if d.get("text"):
        label += f' "{d["text"]}"'
    if d.get("url"):
        label += f" {d['url']}"
    if d.get("keys"):
        label += f" {'+'.join(d['keys'])}"
    return label


def is_terminal_action(d: dict) -> bool:
    return d.get("type") in ("terminate", "done", "answer")


def run(
    *,
    goal: str,
    dashboard_url: str,
    lightcone_api_key: str,
    output_dir: Path,
    max_steps: int = 30,
    display_width: int = 1280,
    display_height: int = 720,
) -> str:
    """Run a Northstar CUA loop. Returns the run_id."""
    run_id = str(uuid.uuid4())
    print(f"[runner] run_id={run_id}")
    print(f"[runner] goal={goal}")
    print(f"[runner] dashboard={dashboard_url}")
    print(f"[runner] output={output_dir}")

    streamer = Streamer(dashboard_url=dashboard_url, run_id=run_id)
    streamer.send_start(task=goal)

    tool = {
        "type": "computer_use",
        "display_width": display_width,
        "display_height": display_height,
        "environment": "browser",
    }

    seeded_goal = (
        f"Navigate the browser to {dashboard_url} and complete this task: {goal}\n\n"
        "When you have finished, call the 'done' function."
    )

    client = Lightcone(api_key=lightcone_api_key)
    try:
        with client.computer.create(kind="desktop") as computer:
            screenshot_url = computer.get_screenshot_url(computer.screenshot())
            items = [{
                "role": "user",
                "content": [
                    {"type": "input_text", "text": seeded_goal},
                    {"type": "input_image", "image_url": screenshot_url, "detail": "auto"},
                ],
            }]

            for step in range(1, max_steps + 1):
                response = client.responses.create(
                    model="tzafon.northstar-cua-fast",
                    tools=[tool, DONE_TOOL],
                    input=items,
                )
                items.extend(response.output or [])
                for text in get_messages(response.output):
                    print(f"[runner] northstar: {text}")

                if is_done(response.output):
                    print(f"[runner] done at step {step}")
                    streamer.send_done()
                    return run_id

                calls, call_ids = get_computer_calls(response.output, tool)
                if not calls:
                    print(f"[runner] no actions at step {step} — exiting")
                    streamer.send_done()
                    return run_id

                if any(is_terminal_action(c) for c in calls):
                    print(f"[runner] terminal action at step {step}: {format_action(calls[0])}")
                    streamer.send_done()
                    return run_id

                for c in calls:
                    label = format_action(c)
                    print(f"[runner] step {step}: {label}")
                    try:
                        annotated = annotate_screenshot(screenshot_url, c, step)
                        save_image(annotated, output_dir / f"step-{step:02d}-{c.get('type','x')}.png")
                        thumb_b64 = to_base64_thumb(annotated, max_width=640)
                    except Exception as e:
                        print(f"[runner] annotation failed (non-fatal): {e}")
                        thumb_b64 = None
                    streamer.send_step(step=step, action_label=label, screenshot_b64=thumb_b64)

                computer.batch(calls)
                time.sleep(1)

                screenshot_url = computer.get_screenshot_url(computer.screenshot())
                for call_id in call_ids:
                    items.append({
                        "type": "computer_call_output",
                        "call_id": call_id,
                        "output": {"type": "input_image", "image_url": screenshot_url, "detail": "auto"},
                    })

        print(f"[runner] hit max_steps={max_steps}")
        streamer.send_error(f"hit max_steps={max_steps} without done")
        return run_id

    except Exception as e:
        print(f"[runner] fatal error: {e}")
        streamer.send_error(str(e))
        raise
    finally:
        streamer.close()
