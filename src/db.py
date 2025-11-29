import os
import asyncpg
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("NEON_DATABASE_URL")

_pool = None

async def get_pool():
    global _pool
    if _pool:
        return _pool
    _pool = await asyncpg.create_pool(
        dsn=DB_URL,
        min_size=1,
        max_size=10
    )
    return _pool


async def fetch(query, *args):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(query, *args)


async def fetchrow(query, *args):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(query, *args)


async def execute(query, *args):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.execute(query, *args)
