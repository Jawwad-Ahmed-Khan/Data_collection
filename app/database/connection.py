"""
ClimaSync Collection Service — Database Connection Pool Manager

Only this file talks to asyncpg directly.
Every other layer uses the methods on DatabasePool.

If the database driver ever changes, only this file needs updating.
"""

from __future__ import annotations

import asyncpg

from app.core.config import Settings
from app.core.exceptions import DatabaseConnectionError, DatabaseError
from app.core.logger import get_logger

logger = get_logger(__name__)

# Pakistan Standard Time — set on every connection
_PKT_TIMEZONE = "Asia/Karachi"


class DatabasePool:
    """Async PostgreSQL connection pool powered by asyncpg.

    Sets timezone to Asia/Karachi on every connection.
    Provides simple fetch/execute methods used by all repositories.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._pool: asyncpg.Pool | None = None

    # ── Lifecycle ─────────────────────────────────────────────────

    async def connect(self) -> None:
        """Create the asyncpg connection pool.

        Sets timezone to Asia/Karachi on every connection via the init callback.
        Refuses to start if the pool cannot be created.
        """
        try:
            self._pool = await asyncpg.create_pool(
                dsn=self._settings.database_dsn,
                min_size=self._settings.collection_db_pool_min,
                max_size=self._settings.collection_db_pool_max,
                server_settings={"timezone": _PKT_TIMEZONE},
                ssl="require",
            )
            logger.info(
                "Database pool created: min=%d, max=%d, timezone=%s",
                self._settings.collection_db_pool_min,
                self._settings.collection_db_pool_max,
                _PKT_TIMEZONE,
            )
        except Exception as exc:
            raise DatabaseConnectionError(
                f"Failed to create database connection pool: {exc}"
            ) from exc

        # Quick connectivity test
        try:
            await self.fetch_one("SELECT 1 AS health_check")
            logger.info("Database connectivity verified")
        except Exception as exc:
            await self.disconnect()
            raise DatabaseConnectionError(
                f"Database connection test failed: {exc}"
            ) from exc

    async def disconnect(self) -> None:
        """Close all connections in the pool."""
        if self._pool is None:
            return
        await self._pool.close()
        logger.info("Database pool closed")
        self._pool = None

    @property
    def pool(self) -> asyncpg.Pool:
        """Return the underlying asyncpg pool.

        Raises:
            DatabaseConnectionError: If the pool has not been created yet.
        """
        if self._pool is None:
            raise DatabaseConnectionError("Database pool not initialized. Call connect() first.")
        return self._pool

    @property
    def is_connected(self) -> bool:
        """Whether the pool exists and has active connections."""
        return self._pool is not None

    # ── Query Methods ─────────────────────────────────────────────

    async def fetch_one(self, query: str, *args: object) -> dict | None:
        """Fetch a single row as a dict, or None if no match.

        Args:
            query: SQL query string with positional $1, $2, ... placeholders.
            *args: Values to substitute for placeholders.

        Returns:
            A dict of column_name -> value, or None.
        """
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(query, *args)
                return dict(row) if row is not None else None
        except asyncpg.PostgresError as exc:
            raise DatabaseError(f"fetch_one failed: {exc}", query=query, original_error=exc) from exc
        except (OSError, ConnectionError) as exc:
            raise DatabaseError(f"fetch_one connection lost: {exc}", query=query, original_error=exc) from exc

    async def fetch_many(self, query: str, *args: object) -> list[dict]:
        """Fetch multiple rows as a list of dicts.

        Args:
            query: SQL query string with positional $1, $2, ... placeholders.
            *args: Values to substitute for placeholders.

        Returns:
            A list of dicts (empty list if no rows match).
        """
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, *args)
                return [dict(r) for r in rows]
        except asyncpg.PostgresError as exc:
            raise DatabaseError(f"fetch_many failed: {exc}", query=query, original_error=exc) from exc
        except (OSError, ConnectionError) as exc:
            raise DatabaseError(f"fetch_many connection lost: {exc}", query=query, original_error=exc) from exc

    async def execute(self, query: str, *args: object) -> str:
        """Execute a single SQL statement and return the status string.

        Args:
            query: SQL query string with positional $1, $2, ... placeholders.
            *args: Values to substitute for placeholders.

        Returns:
            Status string from asyncpg (e.g., "INSERT 0 1", "UPDATE 3").
        """
        try:
            async with self.pool.acquire() as conn:
                return await conn.execute(query, *args)
        except asyncpg.PostgresError as exc:
            raise DatabaseError(f"execute failed: {exc}", query=query, original_error=exc) from exc
        except (OSError, ConnectionError) as exc:
            raise DatabaseError(f"execute connection lost: {exc}", query=query, original_error=exc) from exc

    async def execute_many(self, query: str, args_list: list[tuple]) -> None:
        """Execute the same SQL statement with multiple argument sets.

        Used for batch inserts/updates.

        Args:
            query: SQL query string with positional $1, $2, ... placeholders.
            args_list: List of argument tuples, one per execution.
        """
        if not args_list:
            return
        try:
            async with self.pool.acquire() as conn:
                await conn.executemany(query, args_list)
        except asyncpg.PostgresError as exc:
            raise DatabaseError(
                f"execute_many failed: {exc}", query=query, original_error=exc
            ) from exc
        except (OSError, ConnectionError) as exc:
            raise DatabaseError(
                f"execute_many connection lost: {exc}", query=query, original_error=exc
            ) from exc
