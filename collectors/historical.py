import asyncio
import gzip
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator, Tuple

import httpx

from config import AIRLINE_ICAO_CODES
from db.writer import write_tracks
from models.track import Track

logger = logging.getLogger("historical")
logger.setLevel(logging.DEBUG)

BASE_URL = "https://samples.adsbexchange.com/readsb-hist"
STEP = 60
CONCURRENCY = 20
BATCH_SIZE = 5000
MAX_RETRIES = 3
SOURCE = "adsb-historical"
HTTP_TIMEOUT = 15

class AdsbHistoricalCollector:

    def name(self) -> str:
        return SOURCE

    async def backfill(self, pool):
        progress = load_progress()
        processed = set(progress.get("processed", []))
        logger.info(f"load progress: {len(processed)} months completed")

        for year, month in iterate_months():
            key = f"{year}-{month:02d}"
            if key in processed:
                logger.debug(f"month {key} skipping (processed)")
                continue

            logger.info(f"month {key}: start ({86400 // STEP} files)")

            last_pos: dict[str, Tuple[float, float, float, float]] = {}
            sem = asyncio.Semaphore(CONCURRENCY)
            batch: list[Track] = []
            total_files = 86400 // STEP
            total_months = 121
            added_total = 0
            skipped_total = 0

            client = httpx.AsyncClient(timeout=httpx.Timeout(HTTP_TIMEOUT))

            try:
                tasks = []
                for file_index, offset in enumerate(range(0, 86400, STEP), start=1):
                    url = f"{BASE_URL}/{year}/{month:02d}/01/{offset_to_hms(offset)}Z.json.gz"
                    task = asyncio.create_task(
                        process_one(url, sem, client, pool, last_pos, batch, file_index)
                    )
                    tasks.append(task)

                done = 0
                for comp in asyncio.as_completed(tasks):
                    try:
                        added, skipped = await comp
                        added_total += added
                        skipped_total += skipped
                    except asyncio.CancelledError:
                        logger.warning("stopping remaining tasks")
                        for t in tasks:
                            if not t.done():
                                t.cancel()
                        await asyncio.gather(*tasks, return_exceptions=True)
                        raise
                    except Exception as e:
                        logger.warning(f"task fail: {e}")
                    done += 1
                    if done % 180 == 0 or done == total_files:
                        percent = done / total_files * 100
                        logger.info(f"   progress: {percent:.1f}% ({done}/{total_files})")
            finally:
                await client.aclose()

            if batch:
                for attempt in range(3):
                    try:
                        await write_tracks(pool, batch)
                        break
                    except Exception as e:
                        logger.warning(f"DB write failed: {e}")
                        if attempt == 2:
                            raise
                        await asyncio.sleep(5)

            logger.info(f" month {key}: done | written: {added_total} | dedup_skipped: {skipped_total}")

            progress = load_progress()
            progress["processed"].append(key)
            save_progress("data/historical_progress.json", progress)
            logger.info(f" progress saved: {len(progress['processed'])}/{total_months} months completed")


async def process_one(url, sem, client, pool, last_pos, batch, file_index):
    async with sem:
        try:
            content = await fetch_url(url, client)
            try:
                data = json.loads(gzip.decompress(content))
            except OSError as e:
                try:
                    data = json.loads(content)
                except Exception as ee:
                    logger.warning(f"   file {file_index}: failed to parse JSON: {ee}")
                    return 0, 0
        except FileNotFoundError:
            logger.debug(f"   file {file_index}: 404 (no data for this offset)")
            return 0, 0
        except Exception as e:
            logger.warning(f"   fetch error: {e}")
            return 0, 0

        now = data.get("now")
        if not now:
            return 0, 0

        added = 0
        skipped = 0

        for ac in data.get("aircraft", []):
            flight = ac.get("flight")
            if not flight:
                continue
            callsign = flight.strip()
            if len(callsign) < 3:
                continue
            if callsign[:3].upper() not in AIRLINE_ICAO_CODES:
                continue

            icao24 = ac.get("hex")
            if not icao24:
                continue

            lat = ac.get("lat")
            lon = ac.get("lon")
            if lat is None or lon is None:
                continue

            alt_baro = ac.get("alt_baro")
            if alt_baro == "ground" or alt_baro is None:
                alt_baro = None
            else:
                alt_baro = float(alt_baro)

            gs = ac.get("gs")
            if gs is not None:
                gs = float(gs)

            pos_key = (round(lat, 3), round(lon, 3), alt_baro, gs)
            if last_pos.get(icao24) == pos_key:
                continue
            last_pos[icao24] = pos_key

            seen_pos = ac.get("seen_pos", 0.0)
            timestamp = datetime.fromtimestamp(now - seen_pos, tz=timezone.utc)

            trak = Track(
                icao24=icao24,
                callsign=callsign,
                latitude=lat,
                longitude=lon,
                altitude=alt_baro,
                velocity=gs,
                timestamp=timestamp,
                source=SOURCE
            )
            batch.append(trak)
            added += 1

            if len(batch) >= BATCH_SIZE:
                for attempt in range(3):
                    try:
                        await write_tracks(pool, batch)
                        break
                    except Exception as e:
                        logger.warning(f"DB write failed: {e}")
                        if attempt == 2:
                            raise
                        await asyncio.sleep(5)
                batch.clear()

        return added, skipped

async def fetch_url(url, client):
    backoff = [1, 3, 5]

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = await client.get(url, timeout=HTTP_TIMEOUT)
        except Exception as e:
            if attempt == MAX_RETRIES:
                raise
            logger.warning(f"   fetch error (attempt {attempt}): {e}")
            await asyncio.sleep(backoff[attempt-1])
            continue

        if resp.status_code == 200:
            content = resp.content
            if len(content) >= 2 and content[:2] == b'\x1f\x8b':
                return content
            else:
                if content and (content[0] == 123 or content[0] == 91): # { or [
                    return content
                else:
                    raise FileNotFoundError("Not gzip or JSON file")

        if resp.status_code in (301, 302, 404):
            raise FileNotFoundError(f"HTTP {resp.status_code}")

        if resp.status_code == 429:
            retry = resp.headers.get("Retry-After")
            if retry:
                wait = float(retry)
            else:
                wait = backoff[attempt - 1]
            await asyncio.sleep(wait)
            continue

        if 500 <= resp.status_code < 600:
            await asyncio.sleep(backoff[attempt - 1])
            continue

        raise Exception(f"HTTP {resp.status_code}")
    raise Exception("Max retries")

def load_progress(path: str = "data/historical_progress.json") -> dict:
    p = Path(path)
    if not p.exists():
        return {"processed": []}
    try:
        with open(p, "r", encoding="utf-8") as file:
            return json.load(file)
    except (json.JSONDecodeError, IOError):
        return {"processed": []}

def save_progress(path: str = "data/historical_progress.json", data: dict = None):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")

    with open(tmp, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)
    os.replace(tmp, p)

def offset_to_hms(s: int) -> str:
    hours = s // 3600
    minutes = (s % 3600) // 60
    sec = s % 60
    return f"{hours:02d}{minutes:02d}{sec:02d}"

def iterate_months(start: str = "2016-07", end: str = "2026-07") -> Generator[Tuple[int, int], None, None]:
    s_year, s_month = map(int, start.split("-"))
    e_year, e_month = map(int, end.split("-"))

    while (s_year < e_year) or (s_year == e_year and s_month <= e_month):
        yield s_year, s_month
        s_month += 1
        if s_month > 12:
            s_month = 1
            s_year += 1
