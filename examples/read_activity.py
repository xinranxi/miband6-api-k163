"""Fetch the last 3 days of activity data and print a summary."""
import asyncio
import datetime
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from miband6.device import MiBand6

MAC = "AA:BB:CC:DD:EE:FF"
KEY = "00000000000000000000000000000000"  # 32 hex chars


async def main():
    async with MiBand6(MAC, bytes.fromhex(KEY)) as band:
        await band.authenticate()
        since = datetime.datetime.now() - datetime.timedelta(days=3)
        samples = await band.fetch_activity(since)

        print("fetched %d samples" % len(samples))
        if samples:
            print("range: %s -> %s" % (
                samples[0]["time"].strftime("%Y-%m-%d %H:%M"),
                samples[-1]["time"].strftime("%Y-%m-%d %H:%M")))
            steps = sum(s["steps"] for s in samples)
            hrs = [s["heart_rate"] for s in samples if s["heart_rate"] is not None]
            print("total steps:", steps)
            if hrs:
                print("heart rate: avg %d, min %d, max %d" % (
                    sum(hrs) // len(hrs), min(hrs), max(hrs)))


if __name__ == "__main__":
    asyncio.run(main())
