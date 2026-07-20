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


async def ensure_station_coverage_table(conn) -> None:
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS station_coverage (
            id INT PRIMARY KEY DEFAULT 1,
            geom GEOMETRY(MultiPolygon, 4326),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)


async def update_station_coverage() -> None:
    from db.connection import get_pool

    pool = await get_pool()
    async with pool.acquire() as conn:
        await ensure_station_coverage_table(conn)
        await conn.execute("""
            INSERT INTO station_coverage (id, geom, updated_at)
            VALUES (1, (
                SELECT ST_Union(ST_MakeValid(ST_Buffer(s.location::geography, 350000)::geometry))
                FROM acars_stations s
            ), NOW())
            ON CONFLICT (id) DO UPDATE SET
                geom = EXCLUDED.geom,
                updated_at = EXCLUDED.updated_at
        """)


async def get_acars_coverage(callsign: str) -> float:
    from db.connection import get_pool

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            WITH route AS (
                SELECT ST_MakeLine(point ORDER BY track_timestamp) AS geom
                FROM tracks WHERE callsign = $1
            ), route_length AS (
                SELECT ST_Length(r.geom::geography) AS total FROM route r
            ), covered_length AS (
                SELECT ST_Length(ST_Intersection(r.geom, s.geom)::geography) AS covered
                FROM route r, station_coverage s
                WHERE s.id = 1
            )
            SELECT CASE WHEN total = 0 THEN 0 ELSE covered * 100.0 / total END
            FROM covered_length, route_length
            """,
            callsign,
        )

    return float(row[0])


async def get_all_callsigns() -> list[str]:
    from db.connection import get_pool

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT DISTINCT callsign FROM tracks"
            " WHERE callsign ~ '^[A-Za-z0-9]{2,8}$'"
            "   AND callsign !~ '^[0-9]+$'"
        )

    return [row["callsign"] for row in rows]


async def get_track_distance(callsign: str) -> float:
    from db.connection import get_pool

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT COALESCE(
                ST_Length(ST_MakeLine(point ORDER BY track_timestamp)::geography),
                0
            ) AS total_distance
            FROM (SELECT 1) AS dummy
            WHERE EXISTS (SELECT 1 FROM tracks WHERE callsign = $1)
            """,
            callsign,
        )

    return float(row["total_distance"]) if row else 0.0