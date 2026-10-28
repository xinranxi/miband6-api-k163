"""
Command-line interface for the Mi Band 6 PC client.
"""
import argparse
import asyncio
import csv
import datetime
import json
import os
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


async def cmd_export(args):
    """Fetch historical activity data and write CSV + JSON."""
    from . import activity as activity_mod

    key = bytes.fromhex(args.key)
    band = MiBand6(args.mac, key)
    since = (datetime.datetime.now()
             - datetime.timedelta(days=args.days)).replace(
                 hour=0, minute=0, second=0, microsecond=0)
    print("Fetching activity data since %s ..." % since.strftime("%Y-%m-%d %H:%M"))

    await band.connect()
    try:
        await band.authenticate()
        samples = await band.fetch_activity(since, timeout=args.timeout)
    finally:
        await band.disconnect()

    if not samples:
        print("No samples returned. The band may have nothing newer than %s." % since)
        return

    os.makedirs(args.out, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    base = os.path.join(args.out, "miband6-activity-" + stamp)

    with open(base + ".csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        for row in activity_mod.to_csv_rows(samples):
            w.writerow(row)
    print("Wrote %s.csv (%d samples)" % (base, len(samples)))

    hrs = [s["heart_rate"] for s in samples if s["heart_rate"] is not None]
    total_steps = sum(s["steps"] for s in samples)
    summary = {
        "device": {"mac": args.mac},
        "fetched_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "since": since.isoformat(timespec="seconds"),
        "samples": len(samples),
        "first_sample": samples[0]["time"].isoformat(timespec="seconds"),
        "last_sample": samples[-1]["time"].isoformat(timespec="seconds"),
        "total_steps": total_steps,
        "heart_rate": {
            "count": len(hrs),
            "avg": (sum(hrs) // len(hrs)) if hrs else None,
            "min": min(hrs) if hrs else None,
            "max": max(hrs) if hrs else None,
        },
    }
    with open(base + ".json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print("Wrote %s.json" % base)

    print("\nSummary:")
    print("  samples:     %d  (%s -> %s)" % (
        len(samples),
        samples[0]["time"].strftime("%Y-%m-%d %H:%M"),
        samples[-1]["time"].strftime("%Y-%m-%d %H:%M")))
    print("  total steps: %d" % total_steps)
    if hrs:
        print("  heart rate:  avg %d, min %d, max %d (%d samples)" % (
            sum(hrs) // len(hrs), min(hrs), max(hrs), len(hrs)))


async def cmd_dashboard(args):
    """Generate a self-contained HTML data dashboard from an exported CSV."""
    from . import dashboard as dash_mod
    rows = dash_mod.load_csv(args.data)
    samples = dash_mod.rows_to_samples(rows)
    if not samples:
        print("No samples found in %s" % args.data)
        return
    out = args.out or "dashboard.html"
    dash_mod.write_dashboard(samples, out, title=args.title)
    print("Wrote %s (%d samples)" % (out, len(samples)))


async def cmd_serve(args):
    """Start the local web dashboard (BLE backend + browser UI)."""
    from .webapp import serve
    serve(args.host, args.port)


def _add_device_args(p):
    p.add_argument("--mac", required=True, help="device MAC address")
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

    h = sub.add_parser("hr", help="subscribe to live heart rate")
    _add_device_args(h)
    h.add_argument("--secs", type=int, default=30)
    h.set_defaults(func=cmd_hr)

    e = sub.add_parser("export", help="fetch historical activity data to CSV/JSON")
    _add_device_args(e)
    e.add_argument("--days", type=int, default=3, help="how many days back to fetch")
    e.add_argument("--out", default="./miband6-data", help="output directory")
    e.add_argument("--timeout", type=float, default=30.0, help="fetch timeout (s)")
    e.set_defaults(func=cmd_export)

    d = sub.add_parser("dashboard", help="generate an HTML data dashboard from exported CSV")
    d.add_argument("--data", required=True, help="path to exported activity CSV")
    d.add_argument("--out", default="dashboard.html", help="output HTML path")
    d.add_argument("--title", default="小米手环6 数据大屏", help="dashboard title")
    d.set_defaults(func=cmd_dashboard)

    sv = sub.add_parser("serve", help="start a local web dashboard (fetch via browser)")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8080)
    sv.set_defaults(func=cmd_serve)

    return p


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    asyncio.run(args.func(args))


if __name__ == "__main__":
    main()
