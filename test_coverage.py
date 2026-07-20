import asyncio
import random

from models.track import get_acars_coverage, get_all_callsigns, update_station_coverage


async def main() -> None:

    await update_station_coverage()
    callsigns = await get_all_callsigns()
    random.shuffle(callsigns)
    sample = callsigns[:20]

    for cs in sample:
        coverage = await get_acars_coverage(cs)
        print(f"{cs:<10s} {coverage:.1f}%")



if __name__ == '__main__':
    asyncio.run(main())