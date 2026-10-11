"""Find what keeps the strip's connection alive.

Usage: idle_test.py <mode>
  query      write the status query once right after connecting, then idle
  keepalive  write the status query every second
"""

import asyncio
import sys
import time

from bleak import BleakClient, BleakScanner

ADDR = "23:01:02:22:16:D2"
WRITE = "0000afd1-0000-1000-8000-00805f9b34fb"
NOTIFY = "0000afd2-0000-1000-8000-00805f9b34fb"
QUERY = bytes.fromhex("5f0100f5")


async def main(mode: str, seconds: float = 8) -> None:
    lost = asyncio.Event()
    device = await BleakScanner.find_device_by_address(ADDR, timeout=10)
    client = BleakClient(device, disconnected_callback=lambda c: lost.set(),
                         winrt={"use_cached_services": True})
    for attempt in range(5):
        t0 = time.monotonic()
        try:
            await client.connect(timeout=20)
            print(f"connect took {time.monotonic() - t0:.1f}s")
            await client.write_gatt_char(WRITE, QUERY, response=True)
            break
        except Exception as e:
            print(f"attempt {attempt + 1} failed after {time.monotonic() - t0:.1f}s: {e!r}")
            await client.disconnect()
            await asyncio.sleep(1)
    start = time.monotonic()
    lost.clear()
    t = lambda: f"t={time.monotonic() - start:4.1f}s"
    print(t(), "sent query")
    try:
        await client.start_notify(NOTIFY, lambda _c, data: print(t(), "notify:", data.hex(" ")))
        print(t(), "subscribed")
        await client.write_gatt_char(WRITE, QUERY, response=True)
        print(t(), "sent query again")
    except Exception as e:
        print(t(), "subscribe failed:", e)

    while time.monotonic() - start < seconds and not lost.is_set():
        await asyncio.sleep(1)
        if mode == "keepalive" and not lost.is_set():
            try:
                await client.write_gatt_char(WRITE, QUERY, response=True)
            except Exception as e:
                print(t(), "keepalive write failed:", e)
    print(t(), "disconnected" if lost.is_set() else "still connected")
    if client.is_connected:
        await client.disconnect()


asyncio.run(main(sys.argv[1]))
