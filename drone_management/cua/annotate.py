from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image, ImageDraw


def annotate_screenshot(screenshot_url: str, action: dict, step: int) -> Image.Image:
    """Download a screenshot and draw the action onto it.

    Mirrors visualize.py's annotation style: red circle on clicks, top banner
    for type/key/navigate, small text for scroll. Returns the PIL Image so the
    caller can save it AND base64-encode a smaller copy for streaming.
    """
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


def save_image(img: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)


def to_base64_thumb(img: Image.Image, max_width: int = 640) -> str:
    """Resize and base64-encode for WebSocket streaming."""
    if img.width > max_width:
        ratio = max_width / img.width
        thumb = img.resize((max_width, int(img.height * ratio)))
    else:
        thumb = img
    buf = BytesIO()
    thumb.save(buf, format="PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode("ascii")
