# miband6-api-k163

> **[中文说明 →](README.zh-CN.md)**

**A data interface for the Xiaomi Mi Band 6 — authenticate over Bluetooth and
pull the band's data, without the phone app in the loop. Targets firmware
`1.0.6.x` (sect163r2 ECDH).**

[![Python](https://img.shields.io/badge/python-3.8%2B-blue.svg)](#requirements)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

The Mi Band 6 authentication handshake implemented here uses a pairing key
and ECDH on **sect163r2 (NIST B-163)**, a binary-field elliptic curve.
The project name `miband6-api-k163` is historical and does not identify the
curve; the `k163` module name is retained for compatibility.

## What it can do

- Authenticate against the band over BLE (sect163r2 ECDH)
- Read battery level, step counter and device time
- Subscribe to live heart rate (band must be worn)
- **Fetch historical activity data** — minute-level steps, heart rate and
  sleep-related fields stored on the band — and export them to CSV/JSON over BLE
  (sleep interpretation and history completeness require further validation)

> Historical data covers what the band stores locally (typically the most
> recent days/weeks). Older history lives in the vendor cloud or the phone
> app's local database.

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

# fetch the last 3 days of activity data to CSV + JSON
python -m miband6.cli export --mac AA:BB:CC:DD:EE:FF --key <32-hex-key> --days 3

# local web dashboard (scan, fetch, charts) -> http://127.0.0.1:8080
python -m miband6.cli serve --port 8080
```

`export` writes `miband6-activity-<timestamp>.csv` (one row per minute:
time, kind, intensity, steps, heart_rate, sleep, deep_sleep, rem_sleep) and a
matching `.json` summary.

As a library:

```python
import asyncio
import datetime
from miband6.device import MiBand6

async def main():
    async with MiBand6("AA:BB:CC:DD:EE:FF", bytes.fromhex("<32-hex-key>")) as band:
        await band.authenticate()
        print("battery:", await band.read_battery())
        since = datetime.datetime.now() - datetime.timedelta(days=3)
        samples = await band.fetch_activity(since)
        print("fetched", len(samples), "samples")

asyncio.run(main())
```

## As a data interface

The core of this project is a **data interface to the band**. The CLI and the
web dashboard are thin consumers of it — the dashboard exists mainly to let a
developer confirm data is being read correctly.

Three ways to consume it:

**1. Python**

```python
import asyncio, datetime
from miband6.device import MiBand6

async def main():
    async with MiBand6("AA:BB:CC:DD:EE:FF", bytes.fromhex("<key>")) as band:
        await band.authenticate()
        since = datetime.datetime.now() - datetime.timedelta(days=3)
        samples = await band.fetch_activity(since)
        # samples: list of
        #   {"time": datetime, "kind": int, "steps": int,
        #    "heart_rate": int|None, "sleep": int,
        #    "deep_sleep": int|None, "rem_sleep": int|None}

asyncio.run(main())
```

**2. HTTP (local service)**

```bash
python -m miband6.cli serve --port 8080
```

```bash
curl -X POST http://127.0.0.1:8080/api/fetch \
  -H 'Content-Type: application/json' \
  -d '{"mac":"AA:BB:CC:DD:EE:FF","key":"<32-hex>","days":3}'
# -> {"ok": true, "agg": { "hr_points": [...], "steps_by_day": {...}, ... }}
```

Also available: `POST /api/scan` (discover nearby bands) and
`POST /api/extract_key` (pull the key from a USB-connected phone via adb).

**3. CLI**

```bash
python -m miband6.cli export --mac AA:BB:CC:DD:EE:FF --key <32-hex> --days 3
```

## Verify without hardware

The curve arithmetic is covered by known-answer tests that need no device:

```bash
python -m unittest discover -s tests -v
```

These tests check the supplied vectors; device interoperability requires a
separate hardware test.

## Project layout

```
miband6/
  crypto/k163.py  sect163r2 field + curve arithmetic (pure Python; legacy module name)
  chunked.py   chunked-transfer framing
  auth.py      handshake
  fetch.py     historical data fetch protocol
  activity.py  activity sample decoding
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
