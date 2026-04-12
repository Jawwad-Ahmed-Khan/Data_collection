import asyncio
import asyncpg
from app.core.config import get_settings

async def check_rls():
    settings = get_settings()
    conn = await asyncpg.connect(settings.database_dsn, statement_cache_size=0)
    try:
        print("--- RLS Policies ---")
        policies = await conn.fetch("SELECT tablename, policyname, roles, cmd, qual FROM pg_policies WHERE schemaname = 'public'")
        if not policies:
            print("No RLS policies found in public schema.")
        for p in policies:
            print(f"Table: {p['tablename']} | Policy: {p['policyname']} | Roles: {p['roles']} | Cmd: {p['cmd']} | Qual: {p['qual']}")
            
        print("\n--- Table Enable RLS Flag ---")
        rls_flags = await conn.fetch("SELECT relname, relrowsecurity FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'public' AND relkind = 'r'")
        for f in rls_flags:
            if f['relrowsecurity']:
                print(f"Table {f['relname']} HAS RLS enabled.")
            else:
                pass # Not enabled

    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(check_rls())
