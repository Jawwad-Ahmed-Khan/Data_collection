import asyncio
import asyncpg
import os

from app.core.config import get_settings

async def main():
    settings = get_settings()
    dsn = settings.database_dsn
    print(f"Connecting to {settings.collection_db_host} (Project: {settings.collection_db_user})...")
    conn = await asyncpg.connect(dsn)
    
    with open("database_schema.sql", "r", encoding="utf-8") as f:
        schema = f.read()
        
    print("Executing schema...")
    await conn.execute(schema)
    print("Schema executed successfully!")
    await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
