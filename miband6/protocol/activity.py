"""
Activity sample decoding.

The band streams records as 8-byte samples, one per minute:

    byte 0: kind          activity/sleep classification
    byte 1: intensity     activity intensity
    byte 2: steps         steps in this minute
    byte 3: heart_rate    bpm, 0xFF when not measured
    byte 4: unknown
    byte 5: sleep         sleep state / duration
    byte 6: deep_sleep    deep-sleep indicator (0x80 = n/a)
    byte 7: rem_sleep     REM indicator (0x80 = n/a)

The `kind` byte classifies the sample. Common values observed:
    0x01, 0x03, 0x10 ...  walking / activity
    0x50                  general activity (heart rate valid)
    0x70                  light activity
    0xF0, 0xF9, 0xFA ...  sleep-related (heart rate not measured -> 0xFF)
"""
import datetime

SAMPLE_SIZE = 8
NOT_AVAILABLE = 0x80
NO_HEART_RATE = 0xFF


def parse_activity(raw: bytes, start_time: datetime.datetime):
    """Decode raw sample bytes into a list of dicts.

    Samples are one minute apart starting at `start_time`.
    """
    samples = []
    count = len(raw) // SAMPLE_SIZE
    for i in range(count):
        chunk = raw[i * SAMPLE_SIZE:(i + 1) * SAMPLE_SIZE]
        kind, intensity, steps, heart_rate, unknown, sleep, deep, rem = chunk
        t = start_time + datetime.timedelta(minutes=i)
        samples.append({
            "time": t,
            "kind": kind,
            "intensity": intensity,
            "steps": steps,
            "heart_rate": None if heart_rate == NO_HEART_RATE else heart_rate,
            "sleep": sleep,
            "deep_sleep": None if deep == NOT_AVAILABLE else deep,
            "rem_sleep": None if rem == NOT_AVAILABLE else rem,
        })
    return samples


def to_csv_rows(samples):
    """Yield CSV rows (header first)."""
    yield ["time", "kind", "intensity", "steps", "heart_rate",
           "sleep", "deep_sleep", "rem_sleep"]
    for s in samples:
        yield [
            s["time"].strftime("%Y-%m-%d %H:%M:%S"),
            "0x%02x" % s["kind"],
            s["intensity"],
            s["steps"],
            "" if s["heart_rate"] is None else s["heart_rate"],
            s["sleep"],
            "" if s["deep_sleep"] is None else s["deep_sleep"],
            "" if s["rem_sleep"] is None else s["rem_sleep"],
        ]
