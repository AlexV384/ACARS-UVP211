import asyncio
import time
import httpx
from playwright.async_api import async_playwright
from collectors.base import BaseCollector, RawTrack
from config import AIRLINE_ICAO_CODES, OPENSKY_CLIENT_ID, OPENSKY_CLIENT_SECRET


FEED_URL = "https://aviaradar-client-api.arbina.com/api/aircrafts/feed?prediction_enabled=false&flight_number_enabled=true"
MAIN_URL = "https://aviaradar.ru"

CHROMIUM_ARGS = [
    "--disable-dev-shm-usage",
    "--no-sandbox",
    "--disable-gpu",
    "--disable-setuid-sandbox",
]

_operator_cache: dict[str, str | None] = {}

async def _get_operator_icao(icao24: str) -> str | None:
    if icao24 in _operator_cache:
        return _operator_cache[icao24]
    auth = httpx.BasicAuth(OPENSKY_CLIENT_ID, OPENSKY_CLIENT_SECRET)
    url = f"https://opensky-network.org/api/metadata/aircraft/icao/{icao24}"
    try:
        async with httpx.AsyncClient(auth=auth, timeout=10) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                op = data.get("operatorIcao") or data.get("operator")
                _operator_cache[icao24] = op
                return op
    except Exception:
        pass

    _operator_cache[icao24] = None
    return None


class AviaradarPlaywrightCollector(BaseCollector):
    def __init__(self):
        self._browser = None
        self._pw = None

    def name(self) -> str:
        return "aviaradar"

    async def _ensure_browser(self):
        if self._browser is None:
            p = async_playwright()
            self._pw = await p.start()
            self._browser = await self._pw.chromium.launch(
                headless=True,
                args=CHROMIUM_ARGS,
            )

    async def _safe_fetch(self) -> list[RawTrack]:
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

        aircraft_list = data if isinstance(data, list) else []
        unique_icao = {ac.get("hex_icao24", "").lower() for ac in aircraft_list}
        unique_icao.discard("")
        sem = asyncio.Semaphore(4)
        async def _lookup(icao24: str) -> tuple[str, str | None]:
            async with sem:
                return icao24, await _get_operator_icao(icao24)
        results = await asyncio.gather(*[_lookup(i) for i in unique_icao])
        icao_to_op = dict(results)
        tracks: list[RawTrack] = []
        now_s = int(time.time())

        for ac in aircraft_list:
            icao24 = (ac.get("hex_icao24") or "").lower()
            if not icao24:
                continue
            op = icao_to_op.get(icao24)
            if not op or op not in AIRLINE_ICAO_CODES:
                continue
            raw = RawTrack()
            raw.icao24 = icao24
            raw.callsign = (ac.get("flight_number") or "").strip()
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

    async def fetch(self) -> list[RawTrack]:
        tries = 0
        last_error = None
        while tries < 2:
            tries += 1
            try:
                return await self._safe_fetch()
            except Exception as e:
                last_error = e
                print(f"[aviaradar] attempt {tries} failed: {e}")
                await self.close()
                if tries < 2:
                    await asyncio.sleep(2)
        raise last_error

    async def close(self):
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._pw:
            try:
                await self._pw.stop()
            except Exception:
                pass
            self._pw = None