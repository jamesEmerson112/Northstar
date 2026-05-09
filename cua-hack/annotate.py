"""Annotate a screenshot with a Northstar action."""

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw


def annotate_screenshot(png_bytes: bytes, action: dict, step: int, output_dir: Path) -> Path:
    img = Image.open(BytesIO(png_bytes))
    draw = ImageDraw.Draw(img)

    action_type = action.get("type", "")

    if action_type in ("click", "double_click", "triple_click", "right_click") and action.get("x") is not None:
        px, py = action["x"], action["y"]
        r = 18
        draw.ellipse((px - r, py - r, px + r, py + r), fill="red", outline="darkred", width=3)
        draw.line((px - r, py, px + r, py), fill="white", width=2)
        draw.line((px, py - r, px, py + r), fill="white", width=2)

    elif action_type == "type" and action.get("text"):
        draw.rectangle((0, 0, img.width, 40), fill=(0, 0, 0, 180))
        draw.text((10, 8), f'type: "{action["text"]}"', fill="yellow")

    elif action_type in ("key", "keypress") and action.get("keys"):
        draw.rectangle((0, 0, img.width, 40), fill=(0, 0, 0, 180))
        draw.text((10, 8), f"key: {'+'.join(action['keys'])}", fill="cyan")

    elif action_type == "scroll" and action.get("x") is not None:
        px, py = action["x"], action["y"]
        direction = "down" if (action.get("scroll_y") or 0) > 0 else "up"
        draw.text((px - 10, py - 10), direction, fill="orange")

    elif action_type == "navigate" and action.get("url"):
        draw.rectangle((0, 0, img.width, 40), fill=(0, 0, 0, 180))
        draw.text((10, 8), f"navigate: {action['url']}", fill="lime")

    elif action_type == "drag" and action.get("x1") is not None:
        x1, y1 = action["x1"], action["y1"]
        x2, y2 = action.get("x2", x1), action.get("y2", y1)
        draw.line((x1, y1, x2, y2), fill="magenta", width=4)
        r = 8
        draw.ellipse((x1 - r, y1 - r, x1 + r, y1 + r), outline="magenta", width=2)
        draw.ellipse((x2 - r, y2 - r, x2 + r, y2 + r), fill="magenta")

    label = f"Step {step}: {action_type}"
    draw.rectangle((0, img.height - 32, len(label) * 8 + 20, img.height), fill=(0, 0, 0, 200))
    draw.text((10, img.height - 26), label, fill="white")

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"step-{step:02d}-{action_type}.png"
    img.save(path)
    return path


def save_screenshot(png_bytes: bytes, step: int, suffix: str, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"step-{step:02d}-{suffix}.png"
    Image.open(BytesIO(png_bytes)).save(path)
    return path
