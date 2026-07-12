import asyncio
import time
import httpx
from collectors.base import BaseCollector, RawTrack
from config import AIRLINE_ICAO_CODES


OPENSKY_TOKEN_URL = "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"
OPENSKY_STATES_URL = "https://opensky-network.org/api/states/all"


class OpenSkyCollector(BaseCollector):

    def __init__(self, client_id: str = "", client_secret: str = ""):
        self._client_id = client_id
        self._client_secret = client_secret
        self._token: str | None = None
        self._token_expires_at: float = 0
        self._token_lock = asyncio.Lock()
        self._client = httpx.AsyncClient(timeout=30.0)

    def name(self) -> str:
        return "opensky"

    async def _ensure_token(self):
        if self._token and time.monotonic() < self._token_expires_at - 60:
            return
        async with self._token_lock:
            if self._token and time.monotonic() < self._token_expires_at - 60:
                return
            resp = await self._client.post(
                OPENSKY_TOKEN_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            self._token = data["access_token"]
            expires_in = data.get("expires_in", 1800)
            self._token_expires_at = time.monotonic() + expires_in

    async def _get_states(self) -> dict:
        await self._ensure_token()
        headers = {"Authorization": f"Bearer {self._token}"}
        resp = await self._client.get(OPENSKY_STATES_URL, headers=headers)
        if resp.status_code == 401:
            self._token = None
            await self._ensure_token()
            headers = {"Authorization": f"Bearer {self._token}"}
            resp = await self._client.get(OPENSKY_STATES_URL, headers=headers)
        resp.raise_for_status()
        return resp.json()

    async def fetch(self) -> list[RawTrack]:
        data = await self._get_states()

        tracks: list[RawTrack] = []
        for state in data.get("states", []):
            if not state:
                continue
            icao24 = state[0]
            callsign = state[1]
            if not callsign:
                continue
            callsign = callsign.strip()

            prefix = callsign[:3].upper()
            if prefix not in AIRLINE_ICAO_CODES:
                continue

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