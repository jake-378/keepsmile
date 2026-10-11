from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Callable

from bleak import BleakClient, BleakScanner
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError

from . import protocol
from .protocol import LightState, Protocol


def _uuid16(short: str) -> str:
    return f"0000{short.lower()}-0000-1000-8000-00805f9b34fb"


@dataclass(frozen=True)
class Channel:
    service: str
    write: str
    notify: str


# In the order BluetoothConnection::writeData:forPeripheral: tries them; notify
# characteristics are the ones BluetoothManage::connect_peripheral:didDiscoverService: subscribes to.
CHANNELS = (
    Channel(_uuid16("FFF0"), _uuid16("FFF3"), _uuid16("FFF3")),
    Channel(_uuid16("AE00"), _uuid16("AE01"), _uuid16("AE02")),
    Channel(_uuid16("AFD0"), _uuid16("AFD1"), _uuid16("AFD2")),
)
LEGACY_SERVICE = CHANNELS[0].service

NAME_PREFIX = "KS"


@dataclass
class FoundLight:
    device: BLEDevice
    name: str
    rssi: int

    @property
    def address(self) -> str:
        return self.device.address

    @property
    def protocol(self) -> Protocol:
        return protocol.protocol_for_name(self.name)


async def scan(timeout: float = 5.0) -> list[FoundLight]:
    found = await BleakScanner.discover(timeout=timeout, return_adv=True)
    lights = []
    for device, adv in found.values():
        name = adv.local_name or device.name or ""
        if name.startswith(NAME_PREFIX):
            lights.append(FoundLight(device, name, adv.rssi))
    return sorted(lights, key=lambda light: light.rssi, reverse=True)


class KeepsmileLight:
    def __init__(
        self,
        device: BLEDevice | str,
        name: str | None = None,
        proto: Protocol | None = None,
        rgb: tuple[int, int, int] = (255, 255, 255),
        brightness: int = protocol.MAX_BRIGHTNESS,
        on_disconnect: Callable[[], None] | None = None,
        on_state: Callable[[LightState], None] | None = None,
    ):
        if name is None and isinstance(device, BLEDevice):
            name = device.name
        self.name = name
        self.protocol = proto or protocol.protocol_for_name(name)
        self.rgb = rgb
        self.brightness = brightness
        self.is_on: bool | None = None
        self._on_disconnect = on_disconnect
        self._on_state = on_state
        self._state_event = asyncio.Event()
        self._reconnecting = False
        self._char: BleakGATTCharacteristic | None = None
        self._client = BleakClient(
            device,
            disconnected_callback=self._handle_disconnect,
            winrt={"use_cached_services": True},
        )

    @property
    def address(self) -> str:
        return self._client.address

    @property
    def is_connected(self) -> bool:
        return self._client.is_connected

    def _handle_disconnect(self, _client: BleakClient) -> None:
        if self._on_disconnect and not self._reconnecting:
            self._on_disconnect()

    def _handle_notify(self, _char: BleakGATTCharacteristic, data: bytearray) -> None:
        state = protocol.parse_state(bytes(data))
        if state is None:
            return
        self.is_on, self.rgb, self.brightness = state.on, state.rgb, state.brightness
        self._state_event.set()
        if self._on_state:
            self._on_state(state)

    async def __aenter__(self) -> KeepsmileLight:
        await self.connect()
        return self

    async def __aexit__(self, *exc) -> None:
        await self.disconnect()

    async def connect(self, timeout: float = 20.0, attempts: int = 4) -> None:
        """Connect, perform the app's post-connect handshake, and read the light's state if it reports one.

        The handshake has to happen within ~2 s of the link coming up or the light
        hangs up, and Windows sometimes takes longer than that to finish service
        discovery, so the whole sequence is retried.
        """
        for attempt in range(1, attempts + 1):
            try:
                await self._client.connect(timeout=timeout)
                channel = self._find_channel()
                self._char = self._client.services.get_characteristic(channel.write)
                await self._handshake(channel)
                return
            except (TimeoutError, asyncio.TimeoutError, BleakError, OSError):
                await self._client.disconnect()
                if attempt == attempts:
                    raise
                await asyncio.sleep(1.0)

    async def _handshake(self, channel: Channel) -> None:
        legacy = channel.service == LEGACY_SERVICE
        greeting = protocol.time_sync() if legacy else protocol.QUERY_STATE
        await self._write_once(greeting)

        notify = self._client.services.get_characteristic(channel.notify)
        if notify is None or "notify" not in notify.properties:
            return
        await self._client.start_notify(notify, self._handle_notify)
        if not legacy:
            # The first query was answered before we were subscribed; ask again to learn the state.
            self._state_event.clear()
            await self._write_once(protocol.QUERY_STATE)
            try:
                await asyncio.wait_for(self._state_event.wait(), 1.5)
            except asyncio.TimeoutError:
                pass

    async def disconnect(self) -> None:
        await self._client.disconnect()

    def _find_channel(self) -> Channel:
        services = self._client.services
        for channel in CHANNELS:
            service = services.get_service(channel.service)
            if service is not None and service.get_characteristic(channel.write) is not None:
                return channel
        raise BleakError("No known Keepsmile control characteristic (FFF3/AE01/AFD1) on this device")

    async def write(self, data: bytes) -> None:
        if self._char is None:
            raise RuntimeError("Not connected")
        try:
            await self._write_once(data)
        except (OSError, BleakError):
            # The light may have dropped the link; reconnect once and resend.
            self._reconnecting = True
            try:
                await self._client.disconnect()
                await self.connect()
            finally:
                self._reconnecting = False
            await self._write_once(data)

    async def _write_once(self, data: bytes) -> None:
        await self._client.write_gatt_char(self._char, data, response="write" in self._char.properties)

    async def refresh_state(self, timeout: float = 1.5) -> LightState | None:
        """Ask the light for its state; returns None if it doesn't answer (e.g. legacy devices)."""
        self._state_event.clear()
        await self.write(protocol.QUERY_STATE)
        try:
            await asyncio.wait_for(self._state_event.wait(), timeout)
        except asyncio.TimeoutError:
            return None
        return LightState(bool(self.is_on), self.rgb, self.brightness)

    async def turn_on(self) -> None:
        await self.write(protocol.power(self.protocol, True))
        self.is_on = True

    async def turn_off(self) -> None:
        await self.write(protocol.power(self.protocol, False))
        self.is_on = False

    async def set_color(self, r: int, g: int, b: int) -> None:
        await self.write(protocol.color(self.protocol, r, g, b, self.brightness))
        self.rgb = (r, g, b)

    async def set_brightness(self, level: int) -> None:
        await self.write(protocol.brightness(self.protocol, level, self.rgb))
        self.brightness = level
