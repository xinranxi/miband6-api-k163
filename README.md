# miband6-pc

> **[中文说明（说人话版）→](README.zh-CN.md)**

**A standalone PC client for the Xiaomi Mi Band 6 — connect over Bluetooth and
read your own device, without the phone app in the loop.**

[![Python](https://img.shields.io/badge/python-3.8%2B-blue.svg)](#requirements)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

The Mi Band 6 authenticates every Bluetooth client with a pairing key and a
custom ECDH handshake. Community tools such as Gadgetbridge implement the
*old* (pre-1.0.6) authentication path and therefore fail on newer firmware
with *"invalid authentication key"*. This project implements the newer
handshake correctly.

## The key detail everyone missed

The handshake uses **sect163k1 (NIST K-163)** — a *binary-field* elliptic
curve — not the prime-field P-256 or P-192 curves that other
implementations assume. That single mismatch is why correct pairing keys
were being rejected.

| Implementation | Curve used        | Result on fw 1.0.6.20 |
|----------------|-------------------|------------------------|
| Gadgetbridge   | P-256 (prime)     | ✗ invalid key          |
| band6.py       | P-192 (prime)     | ✗ status `0x07`        |
| **this project** | **sect163k1 (binary)** | **✓ authenticated** |

## What it can do

- Authenticate against the band over BLE
- Read battery level, step counter and device time
- Subscribe to live heart rate (band must be worn)

> Historical data (heart rate, sleep, etc.) is stored by the official app /
> vendor cloud. This tool talks to the band directly for live reads. See
> `docs/PROTOCOL.md` for the data characteristics available on-device.

## Requirements

- Python 3.8+
- A Bluetooth LE adapter
- `pip install -r requirements.txt`

Works on Windows, Linux and macOS. No root. No phone. No vendor app.

## Getting your pairing key

The band pairs with a 32-hex-character key. Two documented ways to obtain
your own key:

**A. From the official app's log files (Android, no root).**
Enable verbose logging in *Mi Fitness / 小米运动健康*
(Profile → About → tap the logo ~10 times), sync once, then pull the log and
look for `huamiAuthKey=`:

```bash
adb pull /sdcard/Android/data/com.mi.health/files/log/XiaomiFit.device.log
grep -o 'huamiAuthKey=[0-9a-f]\{32\}' XiaomiFit.device.log
```

This is the same method documented by the Gadgetbridge project.

**B. If you already exported your device data**, the key is in the app's
`device_db` under the `detail` field of your band's row.

## Usage

```bash
# find your band
python -m miband6.cli scan

# authenticate and read basic info
python -m miband6.cli info --mac AA:BB:CC:DD:EE:FF --key <32-hex-key>

# live heart rate for 60 s (wear the band)
python -m miband6.cli hr --mac AA:BB:CC:DD:EE:FF --key <32-hex-key> --secs 60
```

As a library:

```python
import asyncio
from miband6.device import MiBand6

async def main():
    async with MiBand6("AA:BB:CC:DD:EE:FF", bytes.fromhex("<32-hex-key>")) as band:
        await band.authenticate()
        print("battery:", await band.read_battery())
        print("steps:", await band.read_steps_raw())

asyncio.run(main())
```

## Verify without hardware

The curve arithmetic is covered by known-answer tests that need no device:

```bash
python -m unittest discover -s tests -v
```

If those pass, the ECDH implementation reproduces the same shared secrets as
the firmware.

## Project layout

```
miband6/
  k163.py      sect163k1 field + curve arithmetic (pure Python)
  chunked.py   chunked-transfer framing
  auth.py      handshake
  device.py    high-level MiBand6 client
  cli.py       command-line interface
docs/
  PROTOCOL.md  protocol specification
tests/
  test_k163.py known-answer vectors
```

## Scope & disclaimer

This is an interoperability tool for devices you own. It reads data from a
band you have already paired to your own account, using the pairing key that
your own device was provisioned with. It does not break any encryption, does
not access anyone else's device, and does not redistribute vendor code. Use
it only on hardware you own.

Trademarks belong to their respective owners. This project is not affiliated
with Xiaomi or Huami.

## License

MIT — see [LICENSE](LICENSE).
