from __future__ import annotations

import argparse
import asyncio
import sys

from bleak import BleakScanner

from . import state
from .client import KeepsmileLight, scan
from .protocol import MAX_BRIGHTNESS, Protocol


def parse_color(text: str) -> tuple[int, int, int]:
    text = text.strip().lstrip("#")
    if "," in text:
        parts = [int(p) for p in text.split(",")]
    elif len(text) == 6:
        parts = [int(text[i:i + 2], 16) for i in (0, 2, 4)]
    else:
        raise argparse.ArgumentTypeError("use RRGGBB hex (e.g. ff8800) or r,g,b (e.g. 255,136,0)")
    if len(parts) != 3 or not all(0 <= p <= 255 for p in parts):
        raise argparse.ArgumentTypeError("each colour component must be 0-255")
    return parts[0], parts[1], parts[2]


def parse_brightness(text: str) -> int:
    value = int(text)
    if not 0 <= value <= MAX_BRIGHTNESS:
        raise argparse.ArgumentTypeError(f"brightness must be 0-{MAX_BRIGHTNESS}")
    return value


async def pick_light(args: argparse.Namespace) -> KeepsmileLight:
    if args.address:
        device = await BleakScanner.find_device_by_address(args.address, timeout=args.timeout)
        if device is None:
            sys.exit(f"No device with address {args.address} found")
        name = device.name
    else:
        lights = await scan(args.timeout)
        if not lights:
            sys.exit("No Keepsmile lights found. Make sure the phone app is closed so it isn't holding the connection.")
        strips = [light for light in lights if light.name.startswith("KS03")]
        chosen = (strips or lights)[0]
        print(f"Using {chosen.name} ({chosen.address}, {chosen.protocol.value} protocol)")
        device, name = chosen.device, chosen.name

    rgb, brightness = state.load(device.address)
    return KeepsmileLight(
        device, name, Protocol(args.protocol) if args.protocol else None, rgb=rgb, brightness=brightness
    )


async def run(args: argparse.Namespace) -> None:
    if args.command == "scan":
        lights = await scan(args.timeout)
        if not lights:
            print("No Keepsmile lights found.")
        for light in lights:
            print(f"{light.address}  {light.name:<16} rssi={light.rssi:<4} protocol={light.protocol.value}")
        return

    async with await pick_light(args) as light:
        if args.command == "on":
            await light.turn_on()
        elif args.command == "off":
            await light.turn_off()
        elif args.command == "color":
            await light.set_color(*args.rgb)
        elif args.command == "brightness":
            await light.set_brightness(args.level)
        state.save(light.address, light.rgb, light.brightness)


def main() -> None:
    parser = argparse.ArgumentParser(prog="keepsmile", description="Control Keepsmile Bluetooth LED lights")
    parser.add_argument("--address", help="Bluetooth address of the light (default: nearest KS03 strip)")
    parser.add_argument("--protocol", choices=[p.value for p in Protocol], help="override protocol detection")
    parser.add_argument("--timeout", type=float, default=5.0, help="scan timeout in seconds")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("scan", help="list nearby Keepsmile lights")
    sub.add_parser("on", help="turn the light on")
    sub.add_parser("off", help="turn the light off")
    color = sub.add_parser("color", help="set colour")
    color.add_argument("rgb", type=parse_color, help="RRGGBB hex or r,g,b")
    bright = sub.add_parser("brightness", help="set brightness")
    bright.add_argument("level", type=parse_brightness, help=f"0-{MAX_BRIGHTNESS}")

    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
