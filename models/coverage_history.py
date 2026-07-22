import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone

from db.connection import get_pool


@dataclass
class CoverageHistory:
    hour: datetime
    avg_coverage_pct: float
    updated_at: datetime


async def ensure_table(conn) -> None:
    await conn.execute("""CREATE TABLE IF NOT EXISTS coverage_history (
        hour            TIMESTAMPTZ PRIMARY KEY,
        avg_coverage_pct DOUBLE PRECISION,
        updated_at      TIMESTAMPTZ DEFAULT NOW()
    )""")


_UPDATE_COVERAGE_HISTORY_SQL = """
WITH snapshot AS (
    SELECT date_trunc('hour', NOW()) AS hour,
           AVG(coverage_pct)          AS avg_coverage_pct
    FROM flight_coverage
    WHERE total_length_m > 0
)
INSERT INTO coverage_history (hour, avg_coverage_pct, updated_at)
SELECT hour, avg_coverage_pct, NOW() FROM snapshot
ON CONFLICT (hour) DO UPDATE SET
    avg_coverage_pct = EXCLUDED.avg_coverage_pct,
    updated_at       = NOW()
"""


async def update_coverage_history() -> CoverageHistory:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await ensure_table(conn)
        await conn.execute(_UPDATE_COVERAGE_HISTORY_SQL)
        row = await conn.fetchrow(
            "SELECT hour, avg_coverage_pct, updated_at "
            "FROM coverage_history ORDER BY hour DESC LIMIT 1"
        )
    return CoverageHistory(
        hour=row["hour"],
        avg_coverage_pct=row["avg_coverage_pct"],
        updated_at=row["updated_at"],
    )

if __name__ == '__main__':
    asyncio.run(update_coverage_history())