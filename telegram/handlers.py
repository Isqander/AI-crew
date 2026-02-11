"""Telegram Bot Handlers."""

from __future__ import annotations

import structlog
from aiogram import Router, types
from aiogram.filters import Command

from telegram.gateway_client import GatewayClient

logger = structlog.get_logger()
router = Router()

# Active tasks per chat: {chat_id: thread_id}
_active_tasks: dict[int, str] = {}


def get_gateway(bot_data: dict) -> GatewayClient:
    """Extract GatewayClient from bot context."""
    return bot_data["gateway"]


@router.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "👋 Привет! Я AI-crew бот.\n\n"
        "Команды:\n"
        "/task <описание> — создать задачу\n"
        "/status — статус текущей задачи\n"
        "/help — список команд"
    )


@router.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "📋 Доступные команды:\n\n"
        "/task <описание задачи> — создать новую задачу для AI-команды\n"
        "/status — показать статус текущей задачи\n"
        "/help — показать это сообщение"
    )


@router.message(Command("task"))
async def cmd_task(message: types.Message):
    task_text = message.text.replace("/task", "", 1).strip()
    if not task_text:
        await message.answer("❌ Укажите описание задачи: /task Создать калькулятор API")
        return

    gateway = get_gateway(message.bot.__dict__)
    try:
        result = await gateway.create_run(task=task_text)
        thread_id = result.get("thread_id", "unknown")
        graph_id = result.get("graph_id", "dev_team")
        _active_tasks[message.chat.id] = thread_id
        await message.answer(
            f"✅ Задача создана!\n\n"
            f"🔗 Thread: `{thread_id}`\n"
            f"📊 Граф: {graph_id}\n\n"
            f"Используйте /status для отслеживания.",
            parse_mode="Markdown",
        )
        logger.info("telegram.task_created", chat_id=message.chat.id, thread_id=thread_id)
    except Exception as exc:
        logger.error("telegram.task_error", error=str(exc))
        await message.answer(f"❌ Ошибка: {exc}")


@router.message(Command("status"))
async def cmd_status(message: types.Message):
    thread_id = _active_tasks.get(message.chat.id)
    if not thread_id:
        await message.answer("❌ Нет активной задачи. Создайте через /task")
        return

    gateway = get_gateway(message.bot.__dict__)
    try:
        state = await gateway.get_thread_state(thread_id)
        values = state.get("values", state)
        current_agent = values.get("current_agent", "unknown")
        needs_clarification = values.get("needs_clarification", False)
        summary = values.get("summary", "")
        pr_url = values.get("pr_url", "")

        status_text = f"📊 Статус задачи\n\n🔗 Thread: `{thread_id}`\n🤖 Агент: {current_agent}\n"

        if needs_clarification:
            question = values.get("clarification_question", "")
            status_text += f"\n❓ Вопрос от агента:\n{question}\n\nОтветьте текстом."

        if pr_url:
            status_text += f"\n✅ PR: {pr_url}"

        if summary:
            status_text += f"\n\n📝 {summary[:500]}"

        await message.answer(status_text, parse_mode="Markdown")

    except Exception as exc:
        logger.error("telegram.status_error", error=str(exc))
        await message.answer(f"❌ Ошибка: {exc}")


@router.message()
async def handle_message(message: types.Message):
    """Handle free-text messages as HITL clarification responses."""
    thread_id = _active_tasks.get(message.chat.id)
    if not thread_id:
        await message.answer("💡 Используйте /task для создания задачи или /help для списка команд.")
        return

    gateway = get_gateway(message.bot.__dict__)
    try:
        state = await gateway.get_thread_state(thread_id)
        values = state.get("values", state)
        if values.get("needs_clarification"):
            await gateway.send_clarification(thread_id, message.text)
            await message.answer("✅ Ответ отправлен. Агенты продолжают работу...")
            logger.info("telegram.clarification_sent", chat_id=message.chat.id)
        else:
            await message.answer("ℹ️ Нет активного вопроса. Используйте /status для проверки.")
    except Exception as exc:
        logger.error("telegram.message_error", error=str(exc))
        await message.answer(f"❌ Ошибка: {exc}")
