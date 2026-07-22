import time
import httpx
from collectors.base import BaseCollector, RawTrack, is_valid_callsign
from config import AIRLINE_ICAO_CODES, AIRLINE_IATA_CODES


POCKETWORLD_URL = "https://pocketworld.org/api/flights"
DEFAULT_BBOX = "-20,0,160,80"


class PocketWorldCollector(BaseCollector):

    def __init__(self):
        self._client = httpx.AsyncClient(timeout=60.0)

    def name(self) -> str:
        return "pocketworld"

    async def fetch(self) -> list[RawTrack]:
        params = {"bbox": DEFAULT_BBOX}
        resp = await self._client.get(POCKETWORLD_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

        tracks: list[RawTrack] = []
        now = int(time.time())

        for f in data.get("flights", []):
            callsign = (f.get("callsign") or "").strip()
            if not is_valid_callsign(callsign):
                continue

            if callsign[:3].upper() not in AIRLINE_ICAO_CODES and callsign[:2].upper() not in AIRLINE_IATA_CODES:
                continue

            lat = f.get("lat")
            lon = f.get("lng")
            if lat is None or lon is None:
                continue

            raw = RawTrack()
            raw.icao24 = (f.get("icao24") or "").lower()
            raw.callsign = callsign
            raw.latitude = lat
            raw.longitude = lon
            raw.altitude = f.get("alt")
            raw.velocity = f.get("velocity")
            raw.track_timestamp = f.get("last_contact") or now
            raw.source = self.name()
            tracks.append(raw)

        return tracks
