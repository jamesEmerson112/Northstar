"""CUA runner aimed at the drone_management public dashboard.

Reuses utility functions from Northstar/_cua.py (DONE_TOOL, get_computer_calls,
is_done, format_action, get_messages, is_terminal_action). Adds the loop +
annotated PNG saver, pointed at a configurable URL.

This is standalone — it does NOT import from drone_management/.
"""
from __future__ import annotations

import base64
import time
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image, ImageDraw
from tzafon import Lightcone

# _cua.py is at the Northstar repo root; sys.path includes Northstar/ when this
# package is invoked via `python -m cua` from that directory.
from _cua import (
    DONE_TOOL,
    format_action,
    get_computer_calls,
    get_messages,
    is_done,
    is_terminal_action,
)

from . import dashboard


def _to_thumb_b64(img: Image.Image, max_width: int = 640) -> str:
    if img.width > max_width:
        ratio = max_width / img.width
        thumb = img.resize((max_width, int(img.height * ratio)))
    else:
        thumb = img
    buf = BytesIO()
    thumb.save(buf, format="PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def annotate_screenshot(screenshot_url: str, action: dict, step: int) -> Image.Image:
    """Draw the action on top of a freshly downloaded screenshot."""
    img_data = httpx.get(screenshot_url, timeout=10.0).content
    img = Image.open(BytesIO(img_data)).convert("RGB")
    draw = ImageDraw.Draw(img)

    action_type = action.get("type", "")

    if action_type in ("click", "double_click", "triple_click", "right_click") and action.get("x") is not None:
        px, py = int(action["x"]), int(action["y"])
        r = 18
        draw.ellipse((px - r, py - r, px + r, py + r), fill="red", outline="darkred", width=3)
        draw.line((px - r, py, px + r, py), fill="white", width=2)
        draw.line((px, py - r, px, py + r), fill="white", width=2)

    elif action_type == "type" and action.get("text"):
        draw.rectangle((0, 0, img.width, 40), fill=(0, 0, 0))
        draw.text((10, 8), f'type: "{action["text"]}"', fill="yellow")

    elif action_type in ("key", "keypress") and action.get("keys"):
        draw.rectangle((0, 0, img.width, 40), fill=(0, 0, 0))
        draw.text((10, 8), f"key: {'+'.join(action['keys'])}", fill="cyan")

    elif action_type == "scroll" and action.get("x") is not None:
        px, py = int(action["x"]), int(action["y"])
        direction = "down" if (action.get("scroll_y") or 0) > 0 else "up"
        draw.text((px - 10, py - 10), direction, fill="orange")

    elif action_type == "navigate" and action.get("url"):
        draw.rectangle((0, 0, img.width, 40), fill=(0, 0, 0))
        draw.text((10, 8), f"navigate: {action['url']}", fill="lime")

    label = f"Step {step}: {action_type}"
    draw.rectangle((0, img.height - 32, len(label) * 8 + 20, img.height), fill=(0, 0, 0))
    draw.text((10, img.height - 26), label, fill="white")

    return img


def run(
    *,
    goal: str,
    dashboard_url: str,
    output_dir: Path,
    max_steps: int = 30,
    display_width: int = 1280,
    display_height: int = 720,
) -> None:
    """Open dashboard_url in a Lightcone-hosted desktop browser and pursue goal."""
    print(f"[runner] goal={goal}")
    print(f"[runner] dashboard={dashboard_url}")
    print(f"[runner] output={output_dir}")

    dashboard.publish({
        "type": "start",
        "task": goal,
        "max_steps": max_steps,
        "dashboard_url": dashboard_url,
    })

    try:
        _do_run(goal, dashboard_url, output_dir, max_steps, display_width, display_height)
    except Exception as e:
        print(f"[runner] fatal: {e}")
        dashboard.publish({"type": "error", "message": str(e)})
        raise


def _do_run(goal, dashboard_url, output_dir, max_steps, display_width, display_height):
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

    client = Lightcone()
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
                dashboard.publish({"type": "message", "step": step, "text": text})

            if is_done(response.output):
                print(f"[runner] done at step {step}")
                dashboard.publish({"type": "done", "total_steps": step})
                return

            calls, call_ids = get_computer_calls(response.output, tool)
            if not calls:
                print(f"[runner] no actions at step {step} — exiting")
                dashboard.publish({"type": "done", "total_steps": step})
                return

            if any(is_terminal_action(c) for c in calls):
                print(f"[runner] terminal action at step {step}: {format_action(calls[0])}")
                dashboard.publish({"type": "done", "total_steps": step})
                return

            for c in calls:
                label = format_action(c)
                print(f"[runner] step {step}: {label}")
                thumb_b64 = None
                try:
                    annotated = annotate_screenshot(screenshot_url, c, step)
                    output_dir.mkdir(parents=True, exist_ok=True)
                    annotated.save(output_dir / f"step-{step:02d}-{c.get('type', 'x')}.png")
                    thumb_b64 = _to_thumb_b64(annotated)
                except Exception as e:
                    print(f"[runner] annotation failed (non-fatal): {e}")
                dashboard.publish({
                    "type": "step",
                    "step": step,
                    "action_label": label,
                    "screenshot_b64": thumb_b64,
                })

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
        dashboard.publish({"type": "error", "message": f"hit max_steps={max_steps} without done"})
