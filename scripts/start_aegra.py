import asyncio
import logging
import os

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from agent_server.core.orm import Base
from agent_server.main import app
from agent_server.settings import settings


def configure_logging() -> None:
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def mask_secret(value: str | None) -> str:
    if not value:
        return "missing"
    if len(value) <= 6:
        return "***"
    return f"{value[:3]}***{value[-3:]}"


configure_logging()
logger = logging.getLogger("aegra.startup")


async def init_db() -> None:
    logger.info("Database init start")
    engine = create_async_engine(
        settings.db.database_url,
        pool_pre_ping=True,
    )
    async with engine.begin() as conn:
        # Required for uuid_generate_v4() defaults
        logger.info("Ensuring uuid-ossp extension")
        try:
            await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"'))
        except Exception:
            logger.exception(
                "Failed to create uuid-ossp extension. "
                "Ensure the DB user can CREATE EXTENSION."
            )
            raise

        logger.info("Ensuring metadata tables")
        try:
            await conn.run_sync(Base.metadata.create_all)
        except Exception:
            logger.exception("Failed to initialize metadata tables.")
            raise
    await engine.dispose()
    logger.info("Database init complete")


def main() -> None:
    if not os.getenv("LLM_API_KEY"):
        logger.error("Missing required env: LLM_API_KEY")
        raise SystemExit(1)

    logger.info(
        "Startup config: host=%s port=%s server_url=%s",
        settings.app.HOST,
        settings.app.PORT,
        settings.app.SERVER_URL,
    )
    logger.info("Aegra config: %s", settings.app.AEGRA_CONFIG)
    logger.info(
        "Database config: host=%s port=%s db=%s user=%s",
        settings.db.POSTGRES_HOST,
        settings.db.POSTGRES_PORT,
        settings.db.POSTGRES_DB,
        settings.db.POSTGRES_USER,
    )
    logger.info(
        "Langfuse: enabled=%s logging=%s",
        os.getenv("LANGFUSE_ENABLED", "false"),
        settings.langfuse.LANGFUSE_LOGGING,
    )
    logger.info(
        "LLM: url=%s key=%s",
        os.getenv("LLM_API_URL", "missing"),
        mask_secret(os.getenv("LLM_API_KEY")),
    )

    asyncio.run(init_db())

    import uvicorn

    log_level = os.getenv("UVICORN_LOG_LEVEL", settings.app.LOG_LEVEL).lower()
    uvicorn.run(
        app,
        host=settings.app.HOST,
        port=int(settings.app.PORT),
        log_level=log_level,
    )


if __name__ == "__main__":
    main()
