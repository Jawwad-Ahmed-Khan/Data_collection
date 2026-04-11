import asyncio
import asyncpg
import os

async def main():
    dsn = "postgresql://postgres.ncceiwuskeergtfauojc:Jaw246ahmed%40@aws-1-ap-south-1.pooler.supabase.com:6543/postgres"
    print(f"Connecting to {dsn}...")
    conn = await asyncpg.connect(dsn)
    
    with open("database_schema.sql", "r", encoding="utf-8") as f:
        schema = f.read()
        
    print("Executing schema...")
    await conn.execute(schema)
    print("Schema executed successfully!")
    await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
