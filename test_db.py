import os, asyncio, asyncpg
from dotenv import load_dotenv

load_dotenv()

async def test():
    url = os.getenv("NEON_DATABASE_URL")
    print("Using:", url)
    conn = await asyncpg.connect(dsn=url)
    r = await conn.fetchrow("SELECT now() as now")
    print("DB time:", r["now"])
    await conn.close()

asyncio.run(test())
