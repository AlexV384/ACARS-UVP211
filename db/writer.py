import asyncpg
from models.track import Track


async def write_tracks(pool: asyncpg.Pool, tracks: list[Track]):
    tracks = [t for t in tracks if t.latitude is not None and t.longitude is not None]
    if not tracks:
        return
    async with pool.acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO tracks (icao24, callsign, latitude, longitude,
                                altitude, velocity, track_timestamp, source, point)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8,
                    ST_SetSRID(ST_MakePoint($4, $3), 4326))
            ON CONFLICT (icao24, track_timestamp) DO NOTHING
            """,
            [
                (t.icao24, t.callsign, t.latitude, t.longitude,
                 t.altitude, t.velocity, t.timestamp, t.source)
                for t in tracks
            ],
        )