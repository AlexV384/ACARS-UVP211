import asyncio
import sys
import time
from datetime import datetime, timezone
from config import (COLLECT_INTERVAL, OPENSKY_CLIENT_ID, OPENSKY_CLIENT_SECRET,
                    COLLECTORS)
from collectors.opensky import OpenSkyCollector
from collectors.pocketworld import PocketWorldCollector
from db.connection import get_pool
from db.schema import init_db
from db.writer import write_tracks

from docker_utils import ensure_postgis_sync, wait_for_db
from models.track import Track


async def collect_all(pool, collectors: list):
    for collector in collectors:
        try:
            raw_tracks = await collector.fetch()
        except Exception as e:
            print(f"[{collector.name()}] error: {e}")
            continue

        tracks = [
            Track(
                icao24=t.icao24,
                callsign=t.callsign,
                latitude=t.latitude,
                longitude=t.longitude,
                altitude=t.altitude,
                velocity=t.velocity,
                timestamp=datetime.fromtimestamp(t.track_timestamp, tz=timezone.utc),
                source=t.source,
            )
            for t in raw_tracks
        ]

        await write_tracks(pool, tracks)
        print(f"[{collector.name()}] {len(tracks)} tracks written")


async def main():
    ensure_postgis_sync()
    if not await wait_for_db(get_pool):
        print("Could not connect to PostgreSQL. Check docker logs and try again.")
        sys.exit(1)
    pool = await get_pool()
    await init_db(pool)

    collector = OpenSkyCollector(client_id=OPENSKY_CLIENT_ID, client_secret=OPENSKY_CLIENT_SECRET)
    collector2 = PocketWorldCollector()

    COLLECTORS.append(collector)
    COLLECTORS.append(collector2)

    print(f"starting collector loop, interval={COLLECT_INTERVAL}s")
    while True:
        t0 = time.monotonic()

        await collect_all(pool, COLLECTORS)

        elapsed = time.monotonic() - t0
        sleep = max(0, COLLECT_INTERVAL - elapsed)
        await asyncio.sleep(sleep)


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())