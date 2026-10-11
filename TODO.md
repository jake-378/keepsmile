# TODO

Features we know are possible because the Keepsmile app (v2.3.5) already does them. Byte layouts come from the
decompiled `BluetoothDataTool` packet builders (see [`analysis/README.md`](analysis/README.md)). Constants were read
straight from the binary with `analysis/read_consts.py`.

None of these have been tested on hardware yet. Packets marked **(verify)** have parts the decompiler didn't show
clearly; check the disassembly before relying on them.

Notation: `LL` brightness 0–100, `SS` speed, `RR GG BB` colour, `WW` warm white, `HH MM SS` time, `F0`/`0F` on/off.

## Light features (modern protocol: `KS03~` strips like ours)

- [ ] **Built-in effects / scenes**: `ChangeStyleWithID:speed:brightness:`
  - `5C 00 ID SS LL 00 C5`
  - Still needed: the list of effect IDs and their names (in the app's scene/mode view controllers or its
    localised strings) and the speed range (probably 0–100).
- [ ] **Mode switch**: `ChangeModeWithType:` → `5C 00 (type+1) 00 C5`. Find out what each type means.
- [ ] **Colour with rotation/flow speed**: `ChangeColorWithModel:brightness:RotatSpeed:`
  - `5A 00 01 RR GG BB 00 LL SS A5`
  - Our current colour packet is this one with speed `00`.
- [ ] **Warm white**: `ChangeWarmColorWithModel:brightness:` → `5A 00 02 00 00 00 WW LL 00 A5`.
- [ ] **RGB + warm white at once**: `ChangeRGBCWColorWithModel:brightness:` → `5A 00 00 RR GG BB WW LL 00 A5`.
  - Byte 2 of `5A` packets looks like a mode: `00` = RGB+white, `01` = RGB, `02` = white only.
  - The state reply's mode byte probably uses the same values, so `parse_state` could report it.
- [ ] **On-board microphone music mode**: `WaiMicWithStyleID:ONOFF:level:` → `5A 0A F0/0F STYLE LEVEL A5`.
  - The strip listens with its own mic. Still needed: the style IDs and the sensitivity range.
- [ ] **Sleep timer (turn off after a countdown)**: `SetCountdownTimerWithData:`
  - `5D F0/0F HH MM SS 00 00 00 D5`
- [ ] **Scheduled on/off timers**: `SetTimingWithModel:` builds a 14-byte packet:
  - `header F0/0F HH MM 00 WEEKLOOP F0/0F RR GG BB WW LL isWW footer`
  - Still needed: the `header`/`footer` values (set by the strip timer screen, `KSStripTimeViewController`), and
    the bit order of `WEEKLOOP` (`convertLoopDayStringWithWeekLoop:`).
  - Reading the timers back: query `F6 01 00 6F` (`QueryTimingInfo`); replies are parsed in
    `BluetoothManage::OtherBlackTiming:peripheral:`.
- [ ] **Wiring / colour order (RGB vs GRB, …)**: `setLineType:type:`
  - Decompiles to `E7 00 (type+1) FF FF FF FF FF 7E` **(verify)**: the byte order looks off.
  - Useful if a strip shows the wrong colours.
- [ ] **Device password**: query `8D 01 00 D8` (`QueryPasswordStateInfo`)
  - Set: `8E 00 D1 D2 D3 D4 E8`
  - Check: `8E 01 D1 D2 D3 D4 E8`
  - Change: `8E 02 O1 O2 O3 O4 N1 N2 N3 N4 E8`
  - Each D/O/N is one PIN digit, 0–9. Replies are parsed in `BlackPasswordStateInfo` / `BlackCheckPSWInfo` /
    `BlackChangePSWInfo`. We'd need this to control a light someone has locked with a PIN.
- [ ] **Factory reset**: `ResetDevice`, 11 bytes starting `5A 0B 00 A5` **(verify)**.
  - Ghidra only shows the first 4 bytes being copied. Reply parsed in `ResetDeviceBackInfo:peripheral:`.

## Light features (legacy protocol: `KS03-` strips, `KS04-` bulbs)

- [ ] **Effects**: `ChangeOldStyleWithID:` → `7E 05 03 ID 03 FF FF 00 EF`.
- [ ] **Effect speed**: `ChangeOldWithSpeed:` → `7E 04 02 SS FF FF FF 00 EF`.
- [ ] **Warm white**: `ChangeOldWarmColor` → `7E 07 05 03 00 00 00 FF EF`.
- [ ] **Mic music mode**: `WaiMicOldWithStyleID:level:` → `7E 0A STYLE LEVEL` (4 bytes) **(verify)**.
- [ ] **Timers**:
  - set: `SetOldStripTimingWithModel:` → `7E 08 82 HH MM 00 ON WEEKLOOP EF`
  - query: `QueryOldStripTimingInfoWithONOFF:` → `7E 08 82 FF FF FF (on ? 00 : 01) 00 EF`
  - replies parsed in `OldStripBlackTiming:peripheral:`.
- [ ] **Test the legacy protocol on real hardware.** It's implemented from the decompiled app but nobody has tried
  it on a `KS03-` / `KS04-` light yet.

## Other light types in the app

The app also drives bulbs, ceiling lights, floor lamps, "star"/nebula projectors, wake-up lights, pool/flood lights
and string lights. `SendDataHandler::is…WithPeripheral:` decides the type from the name, and each type has its own
switch/colour/timer packets (`SwitchStarLightWithONOFF:`, `SetCeilingRGBCWTimingWithModel:`,
`ChangeCCTColorWithModel:brightness:`, …). They're all in `decomp_tool_named.c` if someone wants to add support for
their device.

## App and library

- [ ] GUI: effects tab (list + speed slider), warm-white slider, sleep timer, timer editor.
- [ ] GUI: system-tray icon with on/off and presets; start minimised; start with Windows.
- [ ] Global hotkeys for on/off and brightness up/down.
- [ ] Music sync from the PC: capture system audio and stream colours with the normal colour packet. Needs no new
  protocol work; the phone app does the same with the phone's mic.
- [ ] Screen sync (ambient lighting) using the same colour packet.
- [ ] Control several lights at once (groups), like the app's master switch (`MasterSwitchLightWithONOFF:`).
- [ ] Parse the light's other status replies (`Black20DeviceInfo:peripheral:` is a second state format) and timer
  replies.
- [ ] Unit tests for every new packet builder, like `tests/test_protocol.py`.
- [ ] Package for PyPI (`pyproject.toml`, `keepsmile` / `keepsmile-gui` entry points).
- [ ] Standalone `.exe` (PyInstaller) so the GUI runs without Python installed.
- [ ] Try it on macOS and Linux (bleak supports both; only Windows is tested).
