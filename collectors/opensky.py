import httpx
from collectors.base import BaseCollector, RawTrack


OPENSKY_URL = "https://opensky-network.org/api/states/all"


class OpenSkyCollector(BaseCollector):

    def __init__(self, username: str = "", password: str = ""):
        self._username = username
        self._password = password
        self._client = httpx.AsyncClient(
            auth=(username, password) if username else None,
            timeout=30.0,
        )

    def name(self) -> str:
        return "opensky"

    async def fetch(self) -> list[RawTrack]:
        resp = await self._client.get(OPENSKY_URL)
        resp.raise_for_status()
        data = resp.json()

        tracks: list[RawTrack] = []
        for state in data.get("states", []):
            if not state:
                continue
            icao24 = state[0]
            callsign = state[1]
            if not callsign:
                continue
            callsign = callsign.strip()

            lat = state[6]
            lon = state[5]
            if lat is None or lon is None:
                continue

            raw = RawTrack()
            raw.icao24 = icao24
            raw.callsign = callsign
            raw.latitude = lat
            raw.longitude = lon
            raw.altitude = state[7]
            raw.velocity = state[9]
            raw.track_timestamp = state[4]
            raw.source = self.name()
            tracks.append(raw)

        return tracks