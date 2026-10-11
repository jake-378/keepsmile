# Reverse-engineering notes

This folder has the scripts used to work out the Keepsmile Bluetooth protocol from the iOS app
(`com.KS.KSLights` 2.3.5). Their outputs (decompiled code, symbol dumps, Ghidra project) are left out of the repo
because they contain Keepsmile's code; `.gitignore` excludes them. The scripts regenerate them from your own copy.

## What you need

- A **decrypted** IPA of the Keepsmile app. App Store IPAs are encrypted (FairPlay), so the binary must come from
  a decryption tool run on a jailbroken device.
- [Ghidra](https://ghidra-sre.org/) 11+ (12.1 was used), with a JDK it supports.
- Python 3.10+.

## Steps

### 1. Unpack the app

An IPA is a zip file. The executable is `Payload/Keepsmlie.app/Keepsmlie`. "Keepsmlie" is how the app spells it.

```powershell
Expand-Archive com.KS.KSLights-2.3.5.ipa -DestinationPath ipa
```

### 2. Find the interesting code with strings

```powershell
python analysis\strings_scan.py ipa\Payload\Keepsmlie.app\Keepsmlie "KS0|Switch|Color|Bright|Characteristic"
```

`strings_scan.py <binary> [regex]` prints every printable ASCII string with its file offset.
`strings_range.py <binary> <start hex> <end hex>` dumps the strings in an offset range. Objective-C keeps class names, method names and
selectors in the binary, so this quickly turns up `BluetoothDataTool`, `SendDataHandler`, `SwitchNewLight`,
`ChangeWithColor`, `ChangeBrightnessWithModel`, the `KS03-` / `KS04-` name prefixes and the service UUIDs.

### 3. Import into Ghidra (headless)

```powershell
$env:GHIDRA_HEADLESS_MAXMEM = "8G"
& "$GHIDRA\support\analyzeHeadless.bat" analysis\ghidra_proj Keepsmile `
    -import ipa\Payload\Keepsmlie.app\Keepsmlie
```

The first analysis takes a while. Later runs reuse the project and skip analysis:

```powershell
& "$GHIDRA\support\analyzeHeadless.bat" analysis\ghidra_proj Keepsmile -process Keepsmlie -noanalysis -readOnly `
    -scriptPath analysis\ghidra_scripts -postScript <Script>.java <args>
```

### 4. Name the Objective-C call stubs

In arm64 builds, every `[obj selector]` call jumps through a tiny `objc_msgSend` stub, and Ghidra calls each one
`objc_stub::FUN_xxxxxxxx`. That makes the decompiled code unreadable. `ResolveStubs.java` follows each stub to the
selector string it loads and writes a `stub name<TAB>selector` table:

```powershell
... -postScript ResolveStubs.java analysis\stubs.tsv
```

### 5. Decompile the Bluetooth code

`DumpMatching.java <regex file> <output>` decompiles every function whose name matches the regex. The regex goes
in a file because batch-file arguments mangle `|`. The `pattern*.txt` files are the regexes that were used, e.g.
`pattern.txt` covers the write/switch/colour/brightness methods and the CoreBluetooth delegate callbacks.

```powershell
... -postScript DumpMatching.java analysis\pattern.txt analysis\decomp_ble.c
python analysis\apply_stubs.py analysis\stubs.tsv analysis\decomp_ble.c analysis\decomp_ble_named.c
```

`apply_stubs.py` rewrites `objc_stub::FUN_…` calls into their selector names using `stubs.tsv`.

Some packets are copied from constants (Ghidra shows them as `DAT_100dbcb88` and so on).
`read_consts.py <ipa> <length> <address>...` maps those addresses to file offsets and prints the bytes:

```powershell
python analysis\read_consts.py com.KS.KSLights-2.3.5.ipa 8 100dbcb88 100dbcba8
```

`XrefStrings.java` lists the functions that reference a given string. That's how the code that checks the `KS03-` /
`KS04-` name prefixes was found.

## What was found where

| Class / method | What it showed |
| -------------- | -------------- |
| `BluetoothDataTool` | builds the packets: `SwitchNewLight` (on/off), `ChangeWithColor`, `ChangeOldWithBrightness`, `QueryLightInfo`, `KSProofTime` (clock sync), … |
| `SendDataHandler` | picks the legacy or modern packet based on the device name prefix |
| `BluetoothConnection` | the service/characteristic UUID pairs (`FFF0/FFF3`, `AE00/AE01/AE02`, `AFD0/AFD1/AFD2`) and the write type |
| `BluetoothManage::connect_didConnectPeripheral:` | post-connect handshake: state query `5F 01 00 F5` for `AE00`/`AFD0`, clock sync `7E 07 83 …` for `FFF0` |
| `BluetoothManage::BlackDeviceInfo:peripheral:` | layout of the `5F 06 …` state notification (power, RGB, warm white, brightness) |
| brightness slider view | sends at most every 100 ms |

The full protocol is in the [main README](../README.md#protocol).

## Hardware test scripts

- `idle_test.py query|keepalive` connects to a strip and logs notifications and disconnects over time. It was used
  to show that the strip drops the link about 2 seconds after connecting unless it gets the state query. Edit
  `ADDR` for your light.
- `gui_smoke.py` opens the GUI, waits for it to connect, sets a colour and brightness, saves screenshots and closes.
  It needs Pillow (`pip install pillow`).
