import asyncpg
from config import DATABASE_URL

async def fetch_data(query: str):
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        data = await conn.fetch(query)
    finally:
        await conn.close()
    return data
