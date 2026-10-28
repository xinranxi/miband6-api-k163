"""
Historical data fetch.

Pulls activity / health records stored on the band. The band streams
records as fixed-size samples; the transfer is a simple request/ack
exchange over the fetch characteristic (00000004), with the data
arriving on the activity-data characteristic (00000005).

Flow (verified against a real device):
    1. subscribe 00000005 (activity data)
    2. send feature-toggle chunked(0500, 01)
    3. subscribe 00000004 (fetch)  -- the start-of-transfer reply comes here
    4. write fetch command: [0x01, data_type] + time_bytes(since)
    5. band replies 0x10 0x01 0x01  (10 01 01) on 00000004
    6. send 0x02 to start streaming
    7. samples stream on 00000005 (each notification = counter + N samples)
    8. band replies 0x10 0x02 0x01  (10 02 01) to signal completion
"""
import asyncio
import datetime
import struct

from . import chunked
from ..device import UUID_CHUNKED_WRITE, write_message


class DataType:
    """Huami fetch data types (byte values are from the wire protocol)."""
    ACTIVITY = 0x01
    MANUAL_HEART_RATE = 0x02
    SPORTS_SUMMARIES = 0x05
    PAI = 0x0D
    STRESS_MANUAL = 0x12
    STRESS_AUTOMATIC = 0x13
    SPO2_NORMAL = 0x25
    SPO2_SLEEP = 0x26
    STATISTICS = 0x2C
    RESTING_HEART_RATE = 0x3A
    MAX_HEART_RATE = 0x3D


SAMPLE_SIZE = 8  # bytes per activity sample


def time_bytes(dt: datetime.datetime, tz_offset_hours: int = 8) -> bytes:
    """Encode a timestamp for the fetch command.

    IMPORTANT: exactly 8 bytes.
        year (LE uint16) | month | day | hour | minute | 0x00 | timezone
    The timezone byte is offset_hours * 4 (e.g. UTC+8 -> 0x20).

    (An extra trailing byte here makes the firmware reject the command
    with status 0x02, so the length matters.)
    """
    return struct.pack("<H", dt.year) + bytes([
        dt.month & 0xFF,
        dt.day & 0xFF,
        dt.hour & 0xFF,
        dt.minute & 0xFF,
        0x00,
        (tz_offset_hours * 4) & 0xFF,
    ])


def build_fetch_command(data_type: int, since: datetime.datetime,
                        tz_offset_hours: int = 8) -> bytes:
    """[0x01, data_type] + time_bytes(since)."""
    return bytes([0x01, data_type & 0xFF]) + time_bytes(since, tz_offset_hours)


async def fetch(client, collector, data_type: int, since: datetime.datetime,
                xh: int = 0x200, timeout: float = 30.0,
                tz_offset_hours: int = 8) -> bytes:
    """Fetch raw sample data from the band.

    `collector` must expose ``frames`` (chunked-read notifications),
    ``fetch_meta`` (fetch-characteristic replies) and ``activity``
    (activity-data notifications) lists, plus their reset methods.
    """
    from bleak import BleakClient  # noqa: F401  (type only)

    # 1. subscribe activity data
    await client.start_notify("00000005-0000-3512-2118-0009af100700", collector.on_activity)
    await asyncio.sleep(0.3)

    # 2. feature toggle
    await write_message(client, xh, bytes([0x01]), tag=chunked.TAG_FEATURE)
    await asyncio.sleep(0.4)

    # 3. subscribe fetch (start reply arrives here)
    await client.start_notify("00000004-0000-3512-2118-0009af100700", collector.on_fetch_meta)
    await asyncio.sleep(0.3)

    # 4. send fetch command
    collector.reset_data()
    cmd = build_fetch_command(data_type, since, tz_offset_hours)
    await client.write_gatt_char("00000004-0000-3512-2118-0009af100700", cmd, response=False)

    # 5. wait for start reply (10 01 01)
    start = None
    for _ in range(int(timeout / 0.2)):
        await asyncio.sleep(0.2)
        if collector.fetch_meta:
            start = collector.fetch_meta[-1]
            break
    if not start or len(start) < 3 or start[0] != 0x10 or start[2] != 0x01:
        raise RuntimeError("fetch rejected or no start reply: %r"
                           % (start.hex() if start else None))

    # 6. start streaming
    await client.write_gatt_char("00000004-0000-3512-2118-0009af100700",
                                 bytes([0x02]), response=False)

    # 7. collect until completion reply (10 02 01) or timeout
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(0.3)
        if collector.is_done():
            break

    await asyncio.sleep(0.5)

    # 8. concatenate pure data packets (241-byte notifications)
    raw = b""
    for pkt in collector.activity:
        if len(pkt) == 241:
            raw += pkt[1:]  # strip the per-packet counter byte
    return raw
