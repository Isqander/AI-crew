"""AI-crew Telegram Bot — main entry point."""

from __future__ import annotations

import asyncio
import os
import sys

import structlog
from aiogram import Bot, Dispatcher
from dotenv import load_dotenv

from telegram.handlers import router
from telegram.gateway_client import GatewayClient

load_dotenv()

logger = structlog.get_logger()


async def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not set")
        sys.exit(1)

    gateway_url = os.getenv("GATEWAY_URL", "http://gateway:8080")
    bot_email = os.getenv("TELEGRAM_BOT_EMAIL", "bot@ai-crew.local")
    bot_password = os.getenv("TELEGRAM_BOT_PASSWORD", "botpassword123")

    # Init Gateway client
    gateway = GatewayClient(gateway_url)
    try:
        await gateway.login(bot_email, bot_password)
        logger.info("telegram.gateway_connected", url=gateway_url)
    except Exception as exc:
        logger.warning("telegram.gateway_login_failed", error=str(exc))
        # Continue anyway — will retry on first command

    # Init bot
    bot = Bot(token=token)
    bot.__dict__["gateway"] = gateway  # Inject gateway into bot context
    dp = Dispatcher()
    dp.include_router(router)

    logger.info("telegram.bot_starting")
    try:
        await dp.start_polling(bot)
    finally:
        await gateway.close()
        await bot.session.close()
        logger.info("telegram.bot_stopped")


if __name__ == "__main__":
    asyncio.run(main())
