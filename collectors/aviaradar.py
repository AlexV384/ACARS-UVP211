import asyncio
import time
from playwright.async_api import async_playwright
from collectors.base import BaseCollector, RawTrack
from config import AIRLINE_IATA_CODES


FEED_URL = "https://aviaradar-client-api.arbina.com/api/aircrafts/feed?prediction_enabled=false&flight_number_enabled=true"
MAIN_URL = "https://aviaradar.ru"


class AviaradarPlaywrightCollector(BaseCollector):

    def __init__(self):
        self._browser = None

    def name(self) -> str:
        return "aviaradar"

    async def _ensure_browser(self):
        if self._browser is None:
            p = async_playwright()
            self._pw = await p.start()
            self._browser = await self._pw.chromium.launch(headless=True)

    async def fetch(self) -> list[RawTrack]:
        await self._ensure_browser()
        page = await self._browser.new_page()

        async def block_unused(route):
            url = route.request.url
            if any(ext in url for ext in ['.png', '.jpg', '.svg', '.gif', '.woff2', '.woff', '.ttf', '.ico']):
                await route.abort()
            elif any(dom in url for dom in ['yandex', 'mc.yandex', 'google-analytics']):
                await route.abort()
            else:
                await route.continue_()

        await page.route('**/*', block_unused)
        await page.goto(MAIN_URL, wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(3)

        try:
            resp = await page.request.get(FEED_URL)
            data = await resp.json()
        finally:
            await page.close()

        tracks: list[RawTrack] = []
        now_s = int(time.time())

        for ac in data if isinstance(data, list) else []:
            callsign = (ac.get("flight_number") or "").strip()
            if not callsign or callsign == "?":
                continue

            prefix = callsign[:2].upper()
            if prefix not in AIRLINE_IATA_CODES:
                continue

            raw = RawTrack()
            raw.icao24 = (ac.get("hex_icao24") or "").lower()
            raw.callsign = callsign
            raw.latitude = ac.get("latitude")
            raw.longitude = ac.get("longitude")
            raw.altitude = ac.get("altitude_ft")
            raw.velocity = ac.get("velocity_kt")

            ts_ms = ac.get("timestamp")
            if ts_ms:
                raw.track_timestamp = int(ts_ms) // 1000
            else:
                raw.track_timestamp = now_s

            raw.source = self.name()
            tracks.append(raw)

        return tracks

    async def close(self):
        if self._browser:
            await self._browser.close()
            self._browser = None
        if hasattr(self, '_pw'):
            await self._pw.stop()
            self._pw = None
