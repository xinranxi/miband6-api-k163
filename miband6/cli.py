"""
Command-line interface for the Mi Band 6 PC client.
"""
import argparse
import asyncio
import sys

from .device import MiBand6, scan


def _fmt_time(t):
    if not t:
        return "unknown"
    y, mo, d, h, mi, s = t
    return "%04d-%02d-%02d %02d:%02d:%02d" % (y, mo, d, h, mi, s)


async def cmd_scan(args):
    print("Scanning for BLE devices...")
    devices = await scan(args.timeout)
    if not devices:
        print("No Mi Band devices found.")
        return
    for d in devices:
        print("  %-20s %-24s %d dBm" % (d["address"], d["name"] or "(unknown)", d["rssi"]))


async def cmd_info(args):
    key = bytes.fromhex(args.key)
    band = MiBand6(args.mac, key)
    await band.connect()
    try:
        session = await band.authenticate()
        print("Authenticated. Session key: %s" % session.hex())
        print("  Battery: %d%%" % await band.read_battery())
        steps = await band.read_steps_raw()
        print("  Steps (raw u32): %s" % (list(steps),))
        print("  Device time: %s" % _fmt_time(await band.read_time()))
    finally:
        await band.disconnect()


async def cmd_hr(args):
    key = bytes.fromhex(args.key)
    band = MiBand6(args.mac, key)
    await band.connect()
    try:
        await band.authenticate()
        print("Authenticated. Subscribing to heart rate for %ds..." % args.secs)
        await band.subscribe_heart_rate()
        await asyncio.sleep(args.secs)
        samples = [f[1] for f in band.collector.heart_rate if len(f) >= 2]
        if samples:
            print("Heart rate samples: %s" % samples)
        else:
            print("No heart-rate data. Make sure the band is worn on the wrist.")
    finally:
        await band.disconnect()


def _add_device_args(p, need_key=True):
    p.add_argument("--mac", required=True, help="device MAC address")
    if need_key:
        p.add_argument("--key", required=True, help="pairing key (32 hex chars)")


def build_parser():
    p = argparse.ArgumentParser(
        prog="miband6",
        description="Standalone PC client for Xiaomi Mi Band 6 (no phone required).")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("scan", help="scan for nearby devices")
    s.add_argument("--timeout", type=float, default=10.0)
    s.set_defaults(func=cmd_scan)

    i = sub.add_parser("info", help="authenticate and read basic info")
    _add_device_args(i)
    i.set_defaults(func=cmd_info)

    h = sub.add_parser("hr", help="subscribe to heart rate")
    _add_device_args(h)
    h.add_argument("--secs", type=int, default=30)
    h.set_defaults(func=cmd_hr)

    return p


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    asyncio.run(args.func(args))


if __name__ == "__main__":
    main()
