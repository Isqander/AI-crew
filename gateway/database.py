"""
Gateway Database Layer
======================

Async PostgreSQL connection pool (``asyncpg``) and ``users`` table
management.  The pool is initialised once at startup and closed on
shutdown via FastAPI lifespan hooks.
"""

from __future__ import annotations

import asyncpg
import structlog

from gateway.config import settings

logger = structlog.get_logger()

pool: asyncpg.Pool | None = None


async def init_db() -> None:
    """Create the connection pool and ensure the ``users`` table exists."""
    global pool
    pool = await asyncpg.create_pool(settings.database_url, min_size=2, max_size=10)
    logger.info("db.pool_created", dsn=settings.database_url.split("@")[-1])

    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                email VARCHAR(255) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                display_name VARCHAR(100) NOT NULL,
                is_active BOOLEAN DEFAULT true,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)"
        )
    logger.info("db.tables_ready")


async def close_db() -> None:
    """Close the connection pool gracefully."""
    global pool
    if pool:
        await pool.close()
        pool = None
        logger.info("db.pool_closed")


async def get_pool() -> asyncpg.Pool:
    """Return the active pool (raises if not initialised)."""
    if pool is None:
        raise RuntimeError("Database pool is not initialised. Call init_db() first.")
    return pool
