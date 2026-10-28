"""
High-level device interface.
"""
import asyncio
import struct

from bleak import BleakClient, BleakScanner

from . import chunked
from . import auth

# GATT characteristic UUIDs
UUID_CHUNKED_WRITE = "00000016-0000-3512-2118-0009af100700"
UUID_CHUNKED_READ = "00000017-0000-3512-2118-0009af100700"
UUID_AUTH = "00000009-0000-3512-2118-0009af100700"

UUID_HEART_RATE = "00002a37-0000-1000-8000-00805f9b34fb"
UUID_HEART_RATE_CTRL = "00002a39-0000-1000-8000-00805f9b34fb"
UUID_REALTIME_STEPS = "00000007-0000-3512-2118-0009af100700"
UUID_BATTERY = "00002a19-0000-1000-8000-00805f9b34fb"
UUID_CURRENT_TIME = "00002a2b-0000-1000-8000-00805f9b34fb"
UUID_DEVICE_INFO = "00000004-0000-3512-2118-0009af100700"

DEFAULT_MTU = 23


async def write_message(client, xh, data, tag=(0x82, 0x00), mtu=DEFAULT_MTU):
    """Encode and send a single application message over the chunked-write char."""
    for frame in chunked.encode_frames(xh, data, tag=tag, mtu=mtu):
        await client.write_gatt_char(UUID_CHUNKED_WRITE, frame, response=False)
        await asyncio.sleep(0.03)


class FrameCollector:
    """Collects incoming chunked-read notifications."""

    def __init__(self):
        self.frames = []
        self.heart_rate = []

    def __call__(self, char, data):
        raw = bytes(data)
        if char.uuid.lower().startswith("00002a37"):
            self.heart_rate.append(raw)
        else:
            self.frames.append(raw)


class MiBand6:
    """Convenience wrapper around a Mi Band 6 connection."""

    def __init__(self, mac, pairing_key, mtu=DEFAULT_MTU):
        self.mac = mac
        self.pairing_key = pairing_key
        self.mtu = mtu
        self.client = None
        self.collector = FrameCollector()
        self.session_key = None
        self._xh = 0x100

    async def connect(self):
        self.client = BleakClient(self.mac, timeout=40.0)
        await self.client.connect()
        await self.client.start_notify(UUID_CHUNKED_READ, self.collector)
        await asyncio.sleep(0.4)
        return self

    async def authenticate(self):
        self.session_key = await auth.authenticate(
            self.client, self.pairing_key, self.collector, xh_start=self._xh)
        self._xh += 0x10
        return self.session_key

    async def disconnect(self):
        if self.client:
            await self.client.disconnect()

    # ---------- reads ----------
    async def read_battery(self):
        v = await self.client.read_gatt_char(UUID_BATTERY)
        return v[0]

    async def read_steps_raw(self):
        v = await self.client.read_gatt_char(UUID_REALTIME_STEPS)
        b = bytes(v)
        n = len(b) // 4
        return struct.unpack("<%dI" % n, b[:n * 4])

    async def read_time(self):
        v = await self.client.read_gatt_char(UUID_CURRENT_TIME)
        b = bytes(v)
        if len(b) < 7:
            return None
        year = struct.unpack("<H", b[0:2])[0]
        return (year, b[2], b[3], b[4], b[5], b[6])

    async def subscribe_heart_rate(self):
        await self.client.start_notify(UUID_HEART_RATE, self.collector)
        await self.client.write_gatt_char(
            UUID_HEART_RATE_CTRL, bytearray([0x15, 0x01, 0x01]), response=False)
        return self

    async def __aenter__(self):
        return await self.connect()

    async def __aexit__(self, *exc):
        await self.disconnect()


async def scan(timeout=10.0):
    """Scan for nearby Mi Band devices."""
    found = []

    def cb(dev, adv):
        name = adv.local_name or dev.name or ""
        if "Band" in name or "Mi" in name:
            found.append({"address": dev.address, "name": name, "rssi": adv.rssi})

    scanner = BleakScanner(detection_callback=cb)
    await scanner.start()
    await asyncio.sleep(timeout)
    await scanner.stop()
    return found
