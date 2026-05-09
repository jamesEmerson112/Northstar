"""Find where a reference image was taken using a computer-use agent.

This is a GeoGuessr-style investigation runner. It gives Northstar a target
image, opens Google Maps in a desktop browser, lets the agent use Google Maps
and Google Search-style clue lookup, then saves a structured location guess.

Usage:
    .venv/bin/python geolocate.py image.png

Output:
    geolocate_steps/step-01-navigate.png
    geolocate_steps/step-02-click.png
    ...
    geolocate_steps/result.json
"""

import argparse
import base64
import json
import mimetypes
import os
import time
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image, ImageDraw
from tzafon import Lightcone

from _cua import format_action, get_computer_calls, get_messages, is_terminal_action


DEFAULT_MODEL = "tzafon.northstar-cua-fast"
DEFAULT_OUTPUT_DIR = Path("geolocate_steps")
DEFAULT_MAX_STEPS = 100
ENV_FILE = Path(".env")

TOOL = {
    "type": "computer_use",
    "display_width": 1280,
    "display_height": 720,
    "environment": "desktop",
}

SUBMIT_LOCATION_TOOL = {
    "type": "function",
    "name": "submit_location",
    "description": "Submit the final location result for the target image.",
    "parameters": {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": ["found", "best_guess", "blocked"],
                "description": "Use found only when the location is strongly verified in Google Maps.",
            },
            "latitude": {
                "type": ["number", "null"],
                "description": "Latitude for the best verified point, or null if blocked.",
            },
            "longitude": {
                "type": ["number", "null"],
                "description": "Longitude for the best verified point, or null if blocked.",
            },
            "maps_url": {
                "type": ["string", "null"],
                "description": "Google Maps URL for the best candidate, or null if blocked.",
            },
            "confidence": {
                "type": "string",
                "enum": ["high", "medium", "low"],
            },
            "summary": {
                "type": "string",
                "description": "Concise final answer and why this candidate was selected.",
            },
            "evidence": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Concrete visual and Maps clues supporting the result.",
            },
            "uncertainties": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Remaining doubts, blockers, or mismatches.",
            },
        },
        "required": [
            "status",
            "latitude",
            "longitude",
            "maps_url",
            "confidence",
            "summary",
            "evidence",
            "uncertainties",
        ],
    },
}


def build_task(image_path: Path) -> str:
    """Build the geolocation investigation prompt."""
    return f"""
You are a visual geolocation investigator. Your job is to find the exact real-world location where TARGET IMAGE was taken.
YOU MUST CAPTURE THE EXACT STREETVIEW IMAGE THAT CORRESPONDS TO THE LOCATION OF THE TARGET IMAGE.

Rules:
- To open Google Streetview, drag the yellow man at the bottom right onto the map
- Navigate by clicking arrows on the ground, drag click to pan
- To exit Google Streetview, click the back arrow near the top left
- To view other map layers (GPS, traffic etc.), click the bottom left
""".strip()


def load_dotenv(path=ENV_FILE):
    """Load KEY=VALUE lines from .env without adding a dependency."""
    if not path.exists():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def image_to_data_url(path: Path) -> str:
    """Encode a local image as a data URL accepted by input_image."""
    mime_type, _ = mimetypes.guess_type(path.name)
    if not mime_type or not mime_type.startswith("image/"):
        mime_type = "image/png"
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{data}"


def parse_json_arguments(raw_args):
    """Parse function-call arguments from typed SDK objects or raw dicts."""
    if raw_args is None:
        return {}
    if hasattr(raw_args, "model_dump"):
        raw_args = raw_args.model_dump()
    if isinstance(raw_args, dict):
        return raw_args
    if isinstance(raw_args, str):
        try:
            parsed = json.loads(raw_args)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def get_submit_location_calls(output):
    """Extract submit_location calls as (call_id, result_dict)."""
    calls = []
    for item in output or []:
        item_type = item.get("type") if isinstance(item, dict) else getattr(item, "type", None)
        name = item.get("name") if isinstance(item, dict) else getattr(item, "name", None)
        if item_type != "function_call" or name != "submit_location":
            continue

        call_id = item.get("call_id") if isinstance(item, dict) else getattr(item, "call_id", None)
        raw_args = item.get("arguments") if isinstance(item, dict) else getattr(item, "arguments", None)
        calls.append((call_id, parse_json_arguments(raw_args)))

    return calls


def normalize_optional_number(value):
    """Convert numeric strings to numbers while preserving nulls."""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def normalize_string_list(value):
    """Normalize list-ish model output into a list of strings."""
    if value is None:
        return []

    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list):
                return [str(item) for item in parsed]
        return [value]

    if isinstance(value, list):
        items = []
        for item in value:
            if isinstance(item, str) and item.strip().startswith("["):
                try:
                    parsed = json.loads(item)
                except json.JSONDecodeError:
                    parsed = None
                if isinstance(parsed, list):
                    items.extend(str(parsed_item) for parsed_item in parsed)
                    continue
            items.append(str(item))
        return items

    return [str(value)]


def normalize_result(result, *, status="blocked"):
    """Ensure result.json always has the expected shape."""
    normalized = {
        "status": result.get("status") or status,
        "latitude": normalize_optional_number(result.get("latitude")),
        "longitude": normalize_optional_number(result.get("longitude")),
        "maps_url": result.get("maps_url"),
        "confidence": result.get("confidence") or "low",
        "summary": result.get("summary") or "No location result was submitted.",
        "evidence": normalize_string_list(result.get("evidence")),
        "uncertainties": normalize_string_list(result.get("uncertainties")),
    }

    return normalized


def annotate_screenshot(screenshot_url, action_dict, step, output_dir):
    """Download a screenshot and draw the agent's chosen action on it."""
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

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"step-{step:02d}-{action_type}.png"
    img.save(path)
    return path


def save_final_screenshot(screenshot_url, step, output_dir):
    """Save the final browser state."""
    final_data = httpx.get(screenshot_url).content
    final_img = Image.open(BytesIO(final_data))
    output_dir.mkdir(parents=True, exist_ok=True)
    final_path = output_dir / f"step-{step:02d}-final.png"
    final_img.save(final_path)
    return final_path


def save_result(result, output_dir):
    """Write the structured result to result.json."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "result.json"
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def print_result(result):
    """Print a compact human-readable result."""
    print("\nLocation result:")
    print(json.dumps(result, indent=2, sort_keys=True))


def build_initial_items(task, target_image_url, screenshot_url):
    """Build the first multimodal message for the investigation."""
    return [
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": task},
                {"type": "input_text", "text": "TARGET IMAGE:"},
                {"type": "input_image", "image_url": target_image_url, "detail": "high"},
                {"type": "input_text", "text": "CURRENT BROWSER SCREENSHOT:"},
                {"type": "input_image", "image_url": screenshot_url, "detail": "auto"},
            ],
        }
    ]


def build_continue_nudge(screenshot_url, nudge_count, max_steps, reason):
    """Ask the model to continue when it has not advanced the investigation."""
    return {
        "role": "user",
        "content": [
            {
                "type": "input_text",
                "text": (
                    f"The previous response did not advance the investigation: {reason}. "
                    "Continue the geolocation investigation now. Perform the next concrete "
                    "Google Maps/Search browser action, or call submit_location if you are truly done "
                    "with a found or best_guess result. Do not give up before the max step budget "
                    f"unless you have found a verified answer. This is nudge {nudge_count}; "
                    f"the run budget is {max_steps} total model steps."
                ),
            },
            {"type": "input_image", "image_url": screenshot_url, "detail": "auto"},
        ],
    }


def run(image_path, output_dir, max_steps, model):
    """Run the full geolocation CUA loop."""
    load_dotenv()
    client = Lightcone()
    target_image_url = image_to_data_url(image_path)
    task = build_task(image_path)
    result = None
    response = None
    screenshot_url = None
    step = 0
    no_action_count = 0
    stop_reason = None

    with client.computer.create(kind="desktop") as computer:
        screenshot_url = computer.get_screenshot_url(computer.screenshot())
        items = build_initial_items(task, target_image_url, screenshot_url)

        for step in range(1, max_steps + 1):
            response = client.responses.create(
                model=model,
                tools=[TOOL, SUBMIT_LOCATION_TOOL],
                input=items,
            )
            items.extend(response.output or [])

            submit_calls = get_submit_location_calls(response.output)
            if submit_calls:
                call_id, raw_result = submit_calls[-1]
                submitted_result = normalize_result(raw_result)
                if submitted_result["status"] == "blocked" and step < max_steps and screenshot_url:
                    no_action_count += 1
                    print(
                        f"[{step}] blocked result submitted before max steps; nudging agent "
                        f"to continue (nudge {no_action_count}; step {step}/{max_steps})"
                    )
                    if call_id:
                        items.append({
                            "type": "function_call_output",
                            "call_id": call_id,
                            "output": (
                                "Blocked/give-up result rejected before the max step budget. "
                                "Continue investigating in Google Maps/Search unless you can submit "
                                "found or best_guess with evidence."
                            ),
                        })
                    items.append(build_continue_nudge(
                        screenshot_url,
                        no_action_count,
                        max_steps,
                        "submitted blocked before exhausting the step budget",
                    ))
                    continue

                result = submitted_result
                break

            for text in get_messages(response.output):
                print(f"\nAgent: {text}")

            calls, call_ids = get_computer_calls(response.output, TOOL)
            if not calls:
                no_action_count += 1
                if screenshot_url:
                    print(
                        f"[{step}] no tool call returned; nudging agent to continue "
                        f"(nudge {no_action_count}; step {step}/{max_steps})"
                    )
                    items.append(build_continue_nudge(
                        screenshot_url,
                        no_action_count,
                        max_steps,
                        "returned text but no computer action and no submit_location call",
                    ))
                    continue

                stop_reason = "no_screenshot_for_nudge"
                break

            if any(is_terminal_action(c) for c in calls):
                no_action_count += 1
                if screenshot_url:
                    print(
                        f"[{step}] terminal computer action returned; nudging agent to use "
                        f"submit_location or continue (nudge {no_action_count}; step {step}/{max_steps})"
                    )
                    for call_id in call_ids:
                        items.append({
                            "type": "computer_call_output",
                            "call_id": call_id,
                            "output": {"type": "input_image", "image_url": screenshot_url, "detail": "auto"},
                        })
                    items.append(build_continue_nudge(
                        screenshot_url,
                        no_action_count,
                        max_steps,
                        "returned a terminal computer action instead of submit_location",
                    ))
                    continue

                stop_reason = "no_screenshot_for_nudge"
                break

            no_action_count = 0

            for c in calls:
                path = annotate_screenshot(screenshot_url, c, step, output_dir)
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
        else:
            stop_reason = "max_steps"

    if result is None:
        last_messages = get_messages(response.output) if response else []
        if stop_reason == "max_steps":
            stop_detail = f"Reached the max step budget of {max_steps} without a submit_location call."
        elif stop_reason == "no_screenshot_for_nudge":
            stop_detail = (
                f"Stopped at step {step} because no current screenshot was available to nudge "
                "the model after it failed to continue."
            )
        else:
            stop_detail = f"Stopped at step {step} of {max_steps} without a submit_location call."

        result = normalize_result({
            "status": "blocked",
            "confidence": "low",
            "summary": "The agent did not submit a location before the run ended.",
            "evidence": [],
            "uncertainties": [
                stop_detail,
                *last_messages,
            ],
        })

    if screenshot_url:
        final_path = save_final_screenshot(screenshot_url, step, output_dir)
        print(f"\nFinal state  ->  {final_path}")

    result_path = save_result(result, output_dir)
    print(f"Result JSON  ->  {result_path}")
    print_result(result)
    return result


def parse_args():
    load_dotenv()
    model = os.getenv("GEOLOCATE_MODEL", DEFAULT_MODEL)
    output_dir = Path(os.getenv("GEOLOCATE_OUTPUT_DIR", str(DEFAULT_OUTPUT_DIR)))

    parser = argparse.ArgumentParser(description="Use a computer-use agent to geolocate a target image.")
    parser.add_argument("image_path", nargs="?", default="image.png", help="Local image to geolocate.")
    parser.add_argument(
        "--max-steps",
        type=int,
        default=DEFAULT_MAX_STEPS,
        help=f"Maximum CUA steps before returning blocked/best available result. Default: {DEFAULT_MAX_STEPS}.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=output_dir,
        help=f"Directory for annotated screenshots and result.json. Default: {output_dir}.",
    )
    parser.add_argument(
        "--model",
        default=model,
        help=f"Model name to use. Default: {model} or GEOLOCATE_MODEL.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    image_path = Path(args.image_path)
    if not image_path.exists():
        raise FileNotFoundError(f"Target image not found: {image_path}")
    if not image_path.is_file():
        raise ValueError(f"Target image is not a file: {image_path}")
    if args.max_steps < 1:
        raise ValueError("--max-steps must be at least 1")

    run(
        image_path=image_path,
        output_dir=args.output_dir,
        max_steps=args.max_steps,
        model=args.model,
    )


if __name__ == "__main__":
    main()
