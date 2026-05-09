"""Visualize Northstar's decisions — save an annotated screenshot at every step.

Runs a CUA loop and produces a sequence of images showing exactly where
Northstar clicked, what it typed, and how it navigated. Useful for debugging,
demos, and documentation.

Usage:
    pip install Pillow httpx
    export TZAFON_API_KEY=...
    python examples/visualize.py

Output:
    steps/step-01-click.png
    steps/step-02-type.png
    ...
"""

import json
import os
import time
from pathlib import Path
from io import BytesIO

import httpx
from PIL import Image, ImageDraw
from tzafon import Lightcone
from _cua import get_computer_calls, get_messages, format_action, is_terminal_action, DONE_TOOL

client = Lightcone()

TOOL = {
    "type": "computer_use",
    "display_width": 1280,
    "display_height": 720,
    "environment": "desktop",
}

OUTPUT_DIR = Path(os.getenv("LIGHTCONE_OUTPUT_DIR", "steps"))
MAX_STEPS = 50

STREET_VIEW_URL = (
    "https://www.google.com/maps/@37.7762534,-122.4279214,3a,75y,176.57h,89.63t/"
    "data=!3m7!1e1!3m5!1sIVXbt7mX6GZgwfg7D_Xhsg!2e0!6shttps:%2F%2Fstreetviewpixels-pa."
    "googleapis.com%2Fv1%2Fthumbnail%3Fcb_client%3Dmaps_sv.tactile%26w%3D900%26h%3D600%"
    "26pitch%3D0.37011336967007935%26panoid%3DIVXbt7mX6GZgwfg7D_Xhsg%26yaw%3D176."
    "56516082270372!7i16384!8i8192?entry=ttu&g_ep=EgoyMDI2MDUwNi4wIKXMDSoASAFQAw%3D%3D"
)

TASK = f"""
Open this exact Google Maps Street View URL:
{STREET_VIEW_URL}

Explore the area visually in Street View. Dismiss or work around any Google Maps popups,
cookie prompts, or side panels if they get in the way.

Do the following:
1. Look around from the starting location in multiple directions.
2. Navigate forward through Street View to the next intersection.
3. At the intersection, look around from multiple angles.
4. Summarize points of interest in the area, including visible businesses, landmarks,
   signs, street or intersection clues, and anything notable about the streetscape.
5. If Google Maps blocks the task or any detail is uncertain, say so explicitly.

When finished, call done(message=...) with the concise area summary.
""".strip()


def get_done_messages(output):
    """Extract messages supplied to done(message=...) function calls."""
    messages = []
    for item in output or []:
        name = item.get("name") if isinstance(item, dict) else getattr(item, "name", None)
        if name != "done":
            continue

        args = item.get("arguments") if isinstance(item, dict) else getattr(item, "arguments", None)
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}
        elif hasattr(args, "model_dump"):
            args = args.model_dump()

        if isinstance(args, dict):
            message = args.get("message")
            if message:
                messages.append(message)

    return messages


def annotate_screenshot(screenshot_url, action_dict, step):
    """Download a screenshot and draw Northstar's chosen action on it."""
    img_data = httpx.get(screenshot_url).content
    img = Image.open(BytesIO(img_data))
    draw = ImageDraw.Draw(img)

    action_type = action_dict.get("type", "")

    if action_type in ("click", "double_click", "triple_click", "right_click") and action_dict.get("x") is not None:
        px, py = action_dict["x"], action_dict["y"]
        r = 18
        draw.ellipse((px - r, py - r, px + r, py + r), fill="red", outline="darkred", width=3)
        draw.line((px - r, py, px + r, py), fill="white", width=2)
        draw.line((px, py - r, px, py + r), fill="white", width=2)

    elif action_type == "type" and action_dict.get("text"):
        draw.rectangle((0, 0, img.width, 40), fill=(0, 0, 0, 180))
        draw.text((10, 8), f'type: "{action_dict["text"]}"', fill="yellow")

    elif action_type in ("key", "keypress") and action_dict.get("keys"):
        draw.rectangle((0, 0, img.width, 40), fill=(0, 0, 0, 180))
        draw.text((10, 8), f"key: {'+'.join(action_dict['keys'])}", fill="cyan")

    elif action_type == "scroll" and action_dict.get("x") is not None:
        px, py = action_dict["x"], action_dict["y"]
        direction = "down" if (action_dict.get("scroll_y") or 0) > 0 else "up"
        draw.text((px - 10, py - 10), direction, fill="orange")

    elif action_type == "navigate" and action_dict.get("url"):
        draw.rectangle((0, 0, img.width, 40), fill=(0, 0, 0, 180))
        draw.text((10, 8), f"navigate: {action_dict['url']}", fill="lime")

    label = f"Step {step}: {action_type}"
    draw.rectangle((0, img.height - 32, len(label) * 8 + 20, img.height), fill=(0, 0, 0, 200))
    draw.text((10, img.height - 26), label, fill="white")

    OUTPUT_DIR.mkdir(exist_ok=True)
    path = OUTPUT_DIR / f"step-{step:02d}-{action_type}.png"
    img.save(path)
    return path


with client.computer.create(kind="desktop") as computer:
    screenshot_url = computer.get_screenshot_url(computer.screenshot())

    items = [
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": TASK},
                {"type": "input_image", "image_url": screenshot_url, "detail": "auto"},
            ],
        }
    ]

    step = 0
    done_messages = []
    response = None
    for step in range(1, MAX_STEPS + 1):
        response = client.responses.create(
            model="tzafon.northstar-cua-fast",
            tools=[TOOL, DONE_TOOL],
            input=items,
        )
        items.extend(response.output or [])

        done_messages.extend(get_done_messages(response.output))
        if done_messages:
            break

        calls, call_ids = get_computer_calls(response.output, TOOL)
        if not calls:
            break

        if any(is_terminal_action(c) for c in calls):
            print(f"[{step}] {format_action(calls[0])}")
            break

        # Annotate BEFORE executing — shows what Northstar decided to do.
        for c in calls:
            path = annotate_screenshot(screenshot_url, c, step)
            print(f"[{step}] {format_action(c):>30}  ->  {path}")

        computer.batch(calls)
        time.sleep(1)

        screenshot_url = computer.get_screenshot_url(computer.screenshot())
        for call_id in call_ids:
            items.append({
                "type": "computer_call_output",
                "call_id": call_id,
                "output": {"type": "input_image", "image_url": screenshot_url, "detail": "auto"},
            })

    # Save final state
    final_data = httpx.get(screenshot_url).content
    final_img = Image.open(BytesIO(final_data))
    OUTPUT_DIR.mkdir(exist_ok=True)
    final_path = OUTPUT_DIR / f"step-{step:02d}-final.png"
    final_img.save(final_path)
    print(f"\nFinal state  ->  {final_path}")

    for text in done_messages:
        print(f"\nNorthstar: {text}")

    if response:
        messages = get_messages(response.output)
    else:
        messages = []

    for text in messages:
        print(f"\nNorthstar: {text}")

    print(f"\nAll steps saved to {OUTPUT_DIR}/")
