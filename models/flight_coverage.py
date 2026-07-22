import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable
from models.track import get_acars_coverage, Track, get_track_distance, get_all_callsigns, update_station_coverage


@dataclass
class FlightCoverage:
    callsign: str
    flight_date: datetime
    source: str
    coverage_pct: float
    total_length_m: float
    updated_at: datetime
    @classmethod
    async def from_callsign(cls, callsign: str) -> 'FlightCoverage':
        tracks: list['Track'] = await Track.find_by_callsign(callsign)
        if not tracks:
            raise ValueError(f"No tracks found for callsign {callsign!r}")

        cov: float = await get_acars_coverage(callsign)

        return cls(
            callsign=callsign,
            coverage_pct=cov,
            flight_date=tracks[0].timestamp,
            source=tracks[0].source,
            total_length_m=await get_track_distance(callsign),
            updated_at=datetime.now(timezone.utc)
        )


async def ensure_table(conn) -> None:
    await conn.execute("""CREATE TABLE IF NOT EXISTS flight_coverage (
        callsign TEXT,
        flight_date DATE,
        source TEXT,
        coverage_pct DOUBLE PRECISION,
        total_length_m DOUBLE PRECISION,
        updated_at TIMESTAMPTZ DEFAULT NOW(),
        PRIMARY KEY (callsign, flight_date)
    )""")


UPSERT_BATCH_COVERAGE_SQL = """
WITH route AS (
    SELECT callsign, ST_MakeLine(point ORDER BY track_timestamp) AS geom
    FROM tracks
    WHERE callsign = ANY($1::text[])
    GROUP BY callsign
),
route_metrics AS (
    SELECT
        r.callsign,
        ST_Length(r.geom::geography) AS total_length_m,
        CASE WHEN ST_Length(r.geom::geography) = 0 THEN 0
             ELSE ST_Length(ST_Intersection(r.geom, s.geom)::geography) * 100.0
                  / ST_Length(r.geom::geography)
        END AS coverage_pct
    FROM route r, station_coverage s
    WHERE s.id = 1
),
track_meta AS (
    SELECT DISTINCT ON (callsign)
        callsign,
        track_timestamp::date AS flight_date,
        source
    FROM tracks
    WHERE callsign = ANY($1::text[])
    ORDER BY callsign, track_timestamp DESC
)
INSERT INTO flight_coverage (callsign, flight_date, source, coverage_pct, total_length_m, updated_at)
SELECT
    m.callsign,
    t.flight_date,
    t.source,
    m.coverage_pct,
    m.total_length_m,
    NOW()
FROM route_metrics m
JOIN track_meta t ON m.callsign = t.callsign
ON CONFLICT (callsign, flight_date) DO UPDATE SET
    source = EXCLUDED.source,
    coverage_pct = EXCLUDED.coverage_pct,
    total_length_m = EXCLUDED.total_length_m,
    updated_at = EXCLUDED.updated_at
"""


async def update_all_coverage(
    batch_size: int = 20000,
    on_progress: Callable[[int, int], None] | None = None,
) -> None:
    from db.connection import get_pool

    await update_station_coverage()
    callsigns = await get_all_callsigns()
    total = len(callsigns)
    pool = await get_pool()

    async with pool.acquire() as conn:
        await ensure_table(conn)
        for i in range(0, total, batch_size):
            batch = callsigns[i : i + batch_size]
            await conn.execute(UPSERT_BATCH_COVERAGE_SQL, batch)
            if on_progress:
                on_progress(min(i + batch_size, total), total)

    from models.airline_coverage import update_airline_coverage
    from models.coverage_history import update_coverage_history

    await update_airline_coverage()
    await update_coverage_history()
    if on_progress:
        on_progress(total, total)


if __name__ == '__main__':
    asyncio.run(update_all_coverage(on_progress=lambda done, total: print(f"{done}/{total}")))