import csv
import asyncpg
from pathlib import Path


STATIONS_CSV = Path(__file__).resolve().parent.parent / "data" / "stations.csv"

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS acars_stations (
    id SERIAL PRIMARY KEY,
    code TEXT NOT NULL,
    city TEXT,
    airport TEXT,
    country TEXT,
    provider TEXT,
    base TEXT,
    location GEOMETRY(POINT, 4326),
    buffer GEOMETRY(POLYGON, 4326)
);

CREATE TABLE IF NOT EXISTS tracks (
    id BIGSERIAL PRIMARY KEY,
    icao24 TEXT NOT NULL,
    callsign TEXT,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    altitude DOUBLE PRECISION,
    velocity DOUBLE PRECISION,
    track_timestamp TIMESTAMPTZ NOT NULL,
    source TEXT NOT NULL DEFAULT 'opensky',
    point GEOMETRY(POINT, 4326),
    created_at TIMESTAMPTZ DEFAULT NOW()
);


CREATE UNIQUE INDEX IF NOT EXISTS idx_tracks_icao24_ts ON tracks (icao24, track_timestamp);
CREATE INDEX IF NOT EXISTS idx_tracks_point ON tracks USING GIST (point);
CREATE INDEX IF NOT EXISTS idx_tracks_callsign ON tracks (callsign);
CREATE INDEX IF NOT EXISTS idx_tracks_timestamp ON tracks (track_timestamp);
CREATE INDEX IF NOT EXISTS idx_acars_stations_location ON acars_stations USING GIST (location);

CREATE TABLE IF NOT EXISTS station_coverage (
    id INT PRIMARY KEY DEFAULT 1,
    geom GEOMETRY(MultiPolygon, 4326),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS flight_coverage (
    callsign TEXT,
    flight_date DATE,
    source TEXT,
    coverage_pct DOUBLE PRECISION,
    total_length_m DOUBLE PRECISION,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (callsign, flight_date)
);

CREATE TABLE IF NOT EXISTS airline_coverage (
    airline_code TEXT,
    time_period TEXT,
    total_flights INT,
    avg_coverage_pct DOUBLE PRECISION,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (airline_code, time_period)
);

CREATE TABLE IF NOT EXISTS coverage_history (
    hour TIMESTAMPTZ PRIMARY KEY,
    avg_coverage_pct DOUBLE PRECISION,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
"""


async def init_db(pool: asyncpg.Pool):
    async with pool.acquire() as conn:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS postgis")
        await conn.execute(CREATE_TABLES_SQL)

        await conn.execute(
            "SELECT setval('tracks_id_seq', COALESCE((SELECT MAX(id) FROM tracks), 1))"
        )

        await conn.execute("TRUNCATE acars_stations")
        await _import_stations(conn)


async def _import_stations(conn: asyncpg.Connection):
    with open(STATIONS_CSV) as f:
        reader = csv.DictReader(f)
        for row in reader:
            lat = float(row["lat"])
            lon = float(row["lon"])
            await conn.execute(
                """
                INSERT INTO acars_stations (code, city, airport, country, provider, base, location, buffer)
                VALUES ($1, $2, $3, $4, $5, $6,
                    ST_SetSRID(ST_MakePoint($7, $8), 4326),
                    ST_Buffer(ST_SetSRID(ST_MakePoint($7, $8), 4326)::geography, 350000)::geometry
                )
                """,
                row["code"], row["city"], row["airport"], row["country"],
                row["provider"], row["base"], lon, lat,
            )
    print(f"  imported stations from {STATIONS_CSV.name}")