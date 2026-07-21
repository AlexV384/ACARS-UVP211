import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone

from db.connection import get_pool
from config import AIRLINE_ICAO_CODES


@dataclass
class AirlineCoverage:
    airline_code: str
    total_flights: int
    avg_coverage_pct: float
    time_period: str
    updated_at: datetime


async def ensure_table(conn) -> None:
    await conn.execute("""CREATE TABLE IF NOT EXISTS airline_coverage (
        airline_code TEXT,
        time_period TEXT,
        total_flights INT,
        avg_coverage_pct DOUBLE PRECISION,
        updated_at TIMESTAMPTZ DEFAULT NOW(),
        PRIMARY KEY (airline_code, time_period)
    )""")


_UPDATE_AIRLINE_COVERAGE_SQL = """
WITH periods AS (
    SELECT 'all' AS tp, NULL::date AS min_date
    UNION ALL SELECT '1year',  CURRENT_DATE - INTERVAL '1 year'
    UNION ALL SELECT '2years', CURRENT_DATE - INTERVAL '2 years'
    UNION ALL SELECT '5years', CURRENT_DATE - INTERVAL '5 years'
),
airlines AS (
    SELECT unnest($1::text[]) AS code
),
stats AS (
    SELECT a.code,
           p.tp,
           COUNT(fc.callsign)::int AS total_flights,
           AVG(fc.coverage_pct)      AS avg_coverage_pct
    FROM airlines a
    CROSS JOIN periods p
    LEFT JOIN flight_coverage fc
        ON LEFT(fc.callsign, 3) = a.code
       AND (p.min_date IS NULL OR fc.flight_date >= p.min_date)
       AND fc.total_length_m > 0
    GROUP BY a.code, p.tp
)
INSERT INTO airline_coverage (airline_code, time_period, total_flights, avg_coverage_pct, updated_at)
SELECT code, tp, total_flights, avg_coverage_pct, NOW()
FROM stats
ON CONFLICT (airline_code, time_period) DO UPDATE SET
    total_flights    = EXCLUDED.total_flights,
    avg_coverage_pct = EXCLUDED.avg_coverage_pct,
    updated_at       = NOW()
"""


async def update_airline_coverage() -> list[AirlineCoverage]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await ensure_table(conn)
        await conn.execute(_UPDATE_AIRLINE_COVERAGE_SQL, AIRLINE_ICAO_CODES)
        rows = await conn.fetch(
            "SELECT airline_code, total_flights, avg_coverage_pct, time_period, updated_at "
            "FROM airline_coverage ORDER BY airline_code, time_period"
        )
    return [
        AirlineCoverage(
            airline_code=r["airline_code"],
            total_flights=r["total_flights"],
            avg_coverage_pct=r["avg_coverage_pct"],
            time_period=r["time_period"],
            updated_at=r["updated_at"],
        )
        for r in rows
    ]

if __name__ == '__main__':
    asyncio.run(update_airline_coverage())