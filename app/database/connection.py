"""
ClimaSync Collection Service — Database Connection Pool Manager

Only this file talks to asyncpg directly.
Every other layer uses the methods on DatabasePool.

If the database driver ever changes, only this file needs updating.
"""

from __future__ import annotations

import asyncpg
from decimal import Decimal

from app.core.config import Settings
from app.core.exceptions import DatabaseConnectionError, DatabaseError
from app.core.logger import get_logger

logger = get_logger(__name__)

# Pakistan Standard Time — set on every connection
_PKT_TIMEZONE = "Asia/Karachi"


class DatabasePool:
    """Async PostgreSQL connection pool powered by asyncpg.

    Sets timezone to Asia/Karachi on every connection.
    Registers Decimal codec for numeric type handling.
    Provides simple fetch/execute methods used by all repositories.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._pool: asyncpg.Pool | None = None

    # ── Connection Initialization ─────────────────────────────────

    async def _init_connection(self, conn: asyncpg.Connection) -> None:
        """Initialize each connection with custom type handlers.
        
        Registers codecs for:
        - Decimal: PostgreSQL numeric type (no precision loss)
        - ENUM types: magnitude_class, depth_class, breach_level, etc.
        """
        await conn.execute("SET TIME ZONE 'UTC'")
        
        # Register Decimal codec for numeric/decimal columns
        await conn.set_type_codec(
            'numeric',
            encoder=lambda x: str(x) if x is not None else None,
            decoder=lambda x: Decimal(x) if x is not None else None,
            schema='pg_catalog'
        )
        
        # Register ENUM codecs for seismic and weather types
        # These ENUMs are defined in the public schema
        enum_types = [
            'magnitude_class',
            'depth_class',
            'seismic_data_quality',
            'breach_level',
            'flood_status',
            'river_trend',
            'weather_condition',
            'api_source_name',
            'api_health_state',
            'cycle_status',
            'poll_outcome',
            'pk_province',
            'location_tier',
            'poll_priority',
            'asset_type',
            'vulnerability_level',
            'risk_zone',
            'disaster_kind',
            'breach_dispatch_status',
        ]
        
        for enum_type in enum_types:
            try:
                await conn.set_type_codec(
                    enum_type,
                    encoder=lambda x: str(x) if x is not None else None,
                    decoder=lambda x: str(x) if x is not None else None,
                    schema='public'
                )
            except Exception as e:
                # Some enums might not exist in this connection, that's ok
                logger.debug("Could not register codec for %s: %s", enum_type, str(e))

    # ── Lifecycle ─────────────────────────────────────────────────

    async def connect(self) -> None:
        """Create the asyncpg connection pool.

        Sets timezone to Asia/Karachi and registers Decimal codec on every connection.
        Refuses to start if the pool cannot be created.
        """
        try:
            self._pool = await asyncpg.create_pool(
                dsn=self._settings.database_dsn,
                min_size=self._settings.collection_db_pool_min,
                max_size=self._settings.collection_db_pool_max,
                server_settings={"timezone": _PKT_TIMEZONE},
                ssl="require",
                statement_cache_size=0,
                init=self._init_connection,
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
            async with self.pool.acquire(timeout=30.0) as conn:
                row = await conn.fetchrow(query, *args, timeout=30.0)
                return dict(row) if row is not None else None
        except asyncpg.PostgresError as exc:
            raise DatabaseError(f"fetch_one failed: {exc}", query=query, original_error=exc) from exc
        except (OSError, ConnectionError) as exc:
            raise DatabaseError(f"fetch_one connection lost: {exc}", query=query, original_error=exc) from exc
        except Exception as exc:
            raise DatabaseError(f"fetch_one error: {exc}", query=query, original_error=exc) from exc

    async def fetch_many(self, query: str, *args: object) -> list[dict]:
        """Fetch multiple rows as a list of dicts.

        Args:
            query: SQL query string with positional $1, $2, ... placeholders.
            *args: Values to substitute for placeholders.

        Returns:
            A list of dicts (empty list if no rows match).
        """
        try:
            async with self.pool.acquire(timeout=30.0) as conn:
                rows = await conn.fetch(query, *args, timeout=30.0)
                return [dict(r) for r in rows]
        except asyncpg.PostgresError as exc:
            raise DatabaseError(f"fetch_many failed: {exc}", query=query, original_error=exc) from exc
        except (OSError, ConnectionError) as exc:
            raise DatabaseError(f"fetch_many connection lost: {exc}", query=query, original_error=exc) from exc
        except Exception as exc:
            raise DatabaseError(f"fetch_many error: {exc}", query=query, original_error=exc) from exc

    async def execute(self, query: str, *args: object) -> str:
        """Execute a single SQL statement and return the status string.

        Args:
            query: SQL query string with positional $1, $2, ... placeholders.
            *args: Values to substitute for placeholders (including Decimal objects).

        Returns:
            Status string from asyncpg (e.g., "INSERT 0 1", "UPDATE 3").
        """
        try:
            async with self.pool.acquire(timeout=30.0) as conn:
                return await conn.execute(query, *args, timeout=30.0)
        except asyncpg.PostgresError as exc:
            raise DatabaseError(f"execute failed: {exc}", query=query, original_error=exc) from exc
        except (OSError, ConnectionError) as exc:
            raise DatabaseError(f"execute connection lost: {exc}", query=query, original_error=exc) from exc
        except Exception as exc:
            raise DatabaseError(f"execute error: {exc}", query=query, original_error=exc) from exc

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
            async with self.pool.acquire(timeout=30.0) as conn:
                await conn.executemany(query, args_list, timeout=120.0)
        except asyncpg.PostgresError as exc:
            raise DatabaseError(
                f"execute_many failed: {exc}", query=query, original_error=exc
            ) from exc
        except (OSError, ConnectionError) as exc:
            raise DatabaseError(
                f"execute_many connection lost: {exc}", query=query, original_error=exc
            ) from exc
        except Exception as exc:
            raise DatabaseError(
                f"execute_many error: {exc}", query=query, original_error=exc
            ) from exc