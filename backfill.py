import asyncio
import logging
import sys

from collectors.historical import AdsbHistoricalCollector, logger
from db.connection import get_pool
from db.schema import init_db
from docker_utils import ensure_postgis_sync, wait_for_db

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

async def main():
    ensure_postgis_sync()
    if not await wait_for_db(get_pool):
        print("Could not connect to PostgreSQL. Check docker logs and try again.")
        sys.exit(1)
    pool = await get_pool()
    await init_db(pool)

    collector = AdsbHistoricalCollector()
    try:
        await collector.backfill(pool)
    except KeyboardInterrupt:
        logger.info("Progress saved after last completed month")
    except Exception as e:
        logger.exception(f"Backfill failed: {e}")
    finally:
        await pool.close()
        logger.info("DB pool closed")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())