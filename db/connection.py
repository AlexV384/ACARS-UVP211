import asyncpg
from config import DB_CONFIG


async def get_pool() -> asyncpg.Pool:
    return await asyncpg.create_pool(**DB_CONFIG, min_size=1, max_size=5)