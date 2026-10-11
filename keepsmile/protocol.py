"""Byte-level command builders for Keepsmile LED controllers.

Packet layouts were recovered from the Keepsmile iOS app (com.KS.KSLights 2.3.5),
class ``BluetoothDataTool``. Two framings exist and the app picks one from the
device's advertised name (``SendDataHandler::isOldStripWithPeripheral:`` and
``isOldBulbWithPeripheral:``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class Protocol(Enum):
    LEGACY = "legacy"
    """``KS03-`` strips and ``KS04-`` bulbs: 9-byte ``7E .. EF`` frames."""

    MODERN = "modern"
    """``KS03~`` strips and newer models: ``5A``/``5B`` frames."""


LEGACY_NAME_PREFIXES = ("KS03-", "KS04-")

MAX_BRIGHTNESS = 100


def protocol_for_name(name: str | None) -> Protocol:
    if name and name.startswith(LEGACY_NAME_PREFIXES):
        return Protocol.LEGACY
    return Protocol.MODERN


def _byte(value: int, name: str) -> int:
    if not 0 <= value <= 0xFF:
        raise ValueError(f"{name} must be 0-255, got {value}")
    return value


def _level(value: int) -> int:
    if not 0 <= value <= MAX_BRIGHTNESS:
        raise ValueError(f"brightness must be 0-{MAX_BRIGHTNESS}, got {value}")
    return value


def power(protocol: Protocol, on: bool) -> bytes:
    if protocol is Protocol.LEGACY:
        # BluetoothDataTool::SwitchOldLightWithONOFF:
        return bytes([0x7E, 0x04, 0x04, 0xF0 if on else 0x10, 0x01, int(on), 0xFF, 0x00, 0xEF])
    # BluetoothDataTool::SwitchNewLightWithONOFF:
    return bytes([0x5B, 0xF0 if on else 0x0F, 0x00, 0xB5])


def color(protocol: Protocol, r: int, g: int, b: int, brightness: int = MAX_BRIGHTNESS) -> bytes:
    r, g, b = _byte(r, "r"), _byte(g, "g"), _byte(b, "b")
    if protocol is Protocol.LEGACY:
        # BluetoothDataTool::ChangeOldColorWithModel: (legacy frames carry no brightness)
        return bytes([0x7E, 0x07, 0x05, 0x03, r, g, b, 0x00, 0xEF])
    # BluetoothDataTool::ChangeColorWithModel:brightness:
    return bytes([0x5A, 0x00, 0x01, r, g, b, 0x00, _level(brightness), 0x00, 0xA5])


def brightness(protocol: Protocol, level: int, rgb: tuple[int, int, int] = (255, 255, 255)) -> bytes:
    """Build a brightness command.

    Modern devices have no standalone brightness frame; the app resends the
    current colour with the new level, so ``rgb`` must be the colour in use.
    """
    level = _level(level)
    if protocol is Protocol.LEGACY:
        # BluetoothDataTool::ChangeOldWithBrightness:
        return bytes([0x7E, 0x04, 0x01, level, 0xFF, 0xFF, 0xFF, 0x00, 0xEF])
    return color(protocol, *rgb, brightness=level)


# BluetoothDataTool::QueryLightInfo. Devices on the AE00/AFD0 services drop the
# link about 2 s after connecting unless they receive this; they answer with a
# state report (see parse_state).
QUERY_STATE = bytes([0x5F, 0x01, 0x00, 0xF5])


def time_sync(now: datetime | None = None) -> bytes:
    """BluetoothDataTool::KSProofTime, sent by the app on connect to FFF0 devices."""
    now = now or datetime.now()
    weekday = now.isoweekday() % 7 + 1  # NSCalendar: 1 = Sunday
    return bytes([0x7E, 0x07, 0x83, now.hour, now.minute, now.second, weekday, 0xFF, 0xEF])


@dataclass(frozen=True)
class LightState:
    on: bool
    rgb: tuple[int, int, int]
    brightness: int


def parse_state(data: bytes) -> LightState | None:
    """Decode a ``5F 06 ..`` state report (BluetoothManage::BlackDeviceInfo:peripheral:, KS03 branch)."""
    if len(data) < 9 or data[0] != 0x5F or data[1] != 0x06:
        return None
    return LightState(
        on=data[3] == 0xF0,
        rgb=(data[4], data[5], data[6]),
        brightness=min(data[8], MAX_BRIGHTNESS),
    )
