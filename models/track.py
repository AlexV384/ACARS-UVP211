from dataclasses import dataclass
from datetime import datetime


@dataclass
class Track:
    icao24: str
    callsign: str
    latitude: float
    longitude: float
    altitude: float | None
    velocity: float | None
    timestamp: datetime
    source: str

    @classmethod
    async def find_by_callsign(cls, callsign: str) -> list['Track']:
        from db.connection import get_pool

        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT icao24, callsign, latitude, longitude, altitude, "
                "velocity, track_timestamp, source "
                "FROM tracks WHERE callsign = $1 "
                "ORDER BY track_timestamp DESC",
                callsign,
            )

        return [
            cls(
                icao24=row["icao24"],
                callsign=row["callsign"],
                latitude=row["latitude"],
                longitude=row["longitude"],
                altitude=row["altitude"],
                velocity=row["velocity"],
                timestamp=row["track_timestamp"],
                source=row["source"],
            )
            for row in rows
        ]