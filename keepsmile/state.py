"""Remembers each light's last colour and brightness between runs.

The modern protocol resends the colour with every brightness change, so a fresh
process needs the previous colour to avoid resetting the light to white.
"""

from __future__ import annotations

import json
from pathlib import Path

from .protocol import MAX_BRIGHTNESS

STATE_PATH = Path.home() / ".keepsmile.json"

DEFAULT_RGB = (255, 255, 255)


def _load_all() -> dict:
    try:
        return json.loads(STATE_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def load(address: str) -> tuple[tuple[int, int, int], int]:
    saved = _load_all().get(address, {})
    rgb = tuple(saved.get("rgb", DEFAULT_RGB))
    return (rgb[0], rgb[1], rgb[2]), saved.get("brightness", MAX_BRIGHTNESS)


def save(address: str, rgb: tuple[int, int, int], brightness: int) -> None:
    state = _load_all()
    state[address] = {"rgb": list(rgb), "brightness": brightness}
    STATE_PATH.write_text(json.dumps(state, indent=2))
