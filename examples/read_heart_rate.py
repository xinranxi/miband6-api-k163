"""Subscribe to heart rate for 60 seconds. Wear the band first."""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from miband6.device import MiBand6

MAC = "AA:BB:CC:DD:EE:FF"
KEY = "00000000000000000000000000000000"


async def main():
    async with MiBand6(MAC, bytes.fromhex(KEY)) as band:
        await band.authenticate()
        await band.subscribe_heart_rate()
        print("listening for heart rate, wear the band...")
        await asyncio.sleep(60)
        print("samples:", [f[1] for f in band.collector.heart_rate if len(f) >= 2])


if __name__ == "__main__":
    asyncio.run(main())
