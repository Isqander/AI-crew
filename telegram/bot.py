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

    gateway_url = os.getenv("GATEWAY_URL", "http://gateway:8081")
    bot_email = os.getenv("TELEGRAM_BOT_EMAIL", "bot@ai-crew.local")
    bot_password = os.getenv("TELEGRAM_BOT_PASSWORD", "botpassword123")

    # Init Gateway client — auto-register bot account if it doesn't exist
    gateway = GatewayClient(gateway_url)
    try:
        await gateway.ensure_authenticated(bot_email, bot_password)
        logger.info("telegram.gateway_connected", url=gateway_url)
    except Exception as exc:
        logger.warning("telegram.gateway_auth_failed", error=str(exc),
                       hint="Bot will retry authentication on first command")
        # Store credentials so _re_login works later
        gateway._email = bot_email
        gateway._password = bot_password

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
