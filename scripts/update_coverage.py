import asyncio
import logging

from db.connection import get_pool
from db.schema import _import_stations
from models.track import update_station_coverage
from models.flight_coverage import ensure_table as ensure_flight_coverage_table
from models.airline_coverage import update_airline_coverage
from models.coverage_history import update_coverage_history

logger = logging.getLogger("update_coverage")

PER_DATE_SQL = """
WITH date_tracks AS (
    SELECT icao24, callsign, latitude, longitude, altitude, velocity,
           track_timestamp, source, point
    FROM tracks
    WHERE track_timestamp::date = $1::date
      AND point IS NOT NULL
      AND callsign IS NOT NULL
      AND callsign ~ '^[A-Za-z0-9]{2,8}$'
      AND callsign !~ '^[0-9]+$'
),
routes AS (
    SELECT callsign, ST_MakeLine(point ORDER BY track_timestamp) AS geom
    FROM date_tracks
    GROUP BY callsign
),
valid_routes AS (
    SELECT callsign, geom
    FROM routes
    WHERE ST_IsValid(geom)
      AND ST_Length(geom::geography) >= 100
),
route_metrics AS (
    SELECT r.callsign,
           ST_Length(r.geom::geography) AS total_length_m,
           ST_Length(ST_Intersection(r.geom, s.geom)::geography) AS covered_length_m
    FROM valid_routes r, station_coverage s
    WHERE s.id = 1
),
track_meta AS (
    SELECT DISTINCT ON (callsign)
        callsign, $1::date AS flight_date, source
    FROM date_tracks
    ORDER BY callsign, track_timestamp DESC
)
INSERT INTO flight_coverage (callsign, flight_date, source, coverage_pct, total_length_m, updated_at)
SELECT m.callsign, t.flight_date, t.source,
       CASE WHEN m.total_length_m = 0 THEN 0
            ELSE COALESCE(m.covered_length_m, 0) * 100.0 / m.total_length_m
       END,
       m.total_length_m, NOW()
FROM route_metrics m
JOIN track_meta t ON m.callsign = t.callsign
ON CONFLICT (callsign, flight_date) DO UPDATE SET
    coverage_pct = EXCLUDED.coverage_pct,
    total_length_m = EXCLUDED.total_length_m,
    updated_at = NOW()
"""


async def main():
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            station_count = await conn.fetchval("SELECT count(*) FROM acars_stations")
            if station_count == 0:
                logger.info("stations table empty, importing from CSV...")
                await _import_stations(conn)

            await update_station_coverage()
            await ensure_flight_coverage_table(conn)

            rows = await conn.fetch("""
                SELECT DISTINCT track_timestamp::date AS flight_date
                FROM tracks
                WHERE NOT EXISTS (
                    SELECT 1 FROM flight_coverage fc
                    WHERE fc.flight_date = track_timestamp::date
                      AND fc.coverage_pct IS NOT NULL
                )
                ORDER BY flight_date
            """)

        if not rows:
            logger.info("no new dates to process")
        else:
            logger.info(f"found {len(rows)} unprocessed dates")
            for r in rows:
                date = r["flight_date"]
                async with pool.acquire() as conn:
                    result = await conn.execute(PER_DATE_SQL, date)
                count = int(result.split()[-1])
                logger.info(f"  {date}: {count} flights")

        await update_airline_coverage()
        logger.info("airline_coverage updated")
        await update_coverage_history()
        logger.info("coverage_history updated")
        logger.info("done")
    finally:
        await pool.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    asyncio.run(main())