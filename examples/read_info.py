"""Read battery, step counter and device time."""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from miband6.device import MiBand6

MAC = "AA:BB:CC:DD:EE:FF"
KEY = "00000000000000000000000000000000"  # 32 hex chars


async def main():
    async with MiBand6(MAC, bytes.fromhex(KEY)) as band:
        await band.authenticate()
        print("battery: %d%%" % await band.read_battery())
        print("steps:   %s" % (list(await band.read_steps_raw()),))
        print("time:    %s" % (await band.read_time(),))


if __name__ == "__main__":
    asyncio.run(main())
