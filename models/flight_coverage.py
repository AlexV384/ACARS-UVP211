import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from models.track import get_acars_coverage, Track, get_track_distance, get_all_callsigns


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


async def upsert_coverage(conn, inst: FlightCoverage) -> None:
    await conn.execute(
        """INSERT INTO flight_coverage (callsign, flight_date, source, coverage_pct, total_length_m, updated_at)
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (callsign, flight_date) DO UPDATE SET
            source = EXCLUDED.source,
            coverage_pct = EXCLUDED.coverage_pct,
            total_length_m = EXCLUDED.total_length_m,
            updated_at = EXCLUDED.updated_at""",
        inst.callsign, inst.flight_date, inst.source,
        inst.coverage_pct, inst.total_length_m, inst.updated_at
    )


async def update_coverage_batch(callsigns: list[str], batch_size: int = 50) -> None:
    from db.connection import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        await ensure_table(conn)
        for i in range(0, len(callsigns), batch_size):
            print(f'Progress: {i} of {len(callsigns)}')
            batch = callsigns[i:i + batch_size]
            async with conn.transaction():
                for callsign in batch:
                    inst = await FlightCoverage.from_callsign(callsign)
                    await upsert_coverage(conn, inst)


async def update_all_coverage() -> None:
    callsigns = await get_all_callsigns()
    await update_coverage_batch(callsigns)

if __name__ == '__main__': # For testing only
    asyncio.run(update_all_coverage())