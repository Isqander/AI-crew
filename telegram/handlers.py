"""Telegram Bot Handlers.

Task creation flow (two-step dialog):
  1. ``/task`` → bot asks to enter task description
  2. User enters task → bot shows graph selection (numbered list)
  3. User picks a number → task is created via ``POST /api/run``
"""

from __future__ import annotations

import structlog
from aiogram import Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from telegram.gateway_client import GatewayClient

logger = structlog.get_logger()
router = Router()

# Active tasks per chat: {chat_id: thread_id}
_active_tasks: dict[int, str] = {}

# Special value for "LLM chooses graph" option
_LLM_AUTO = "__llm_auto__"


# ─────── FSM States ─────────────────────────────────────────

class TaskCreation(StatesGroup):
    """Two-step dialog: enter task → pick graph."""
    waiting_for_task = State()
    waiting_for_graph = State()


# ─────── Helpers ────────────────────────────────────────────


def get_gateway(gateway: GatewayClient) -> GatewayClient:
    """Return the GatewayClient passed by aiogram's dependency injection.

    In aiogram 3, extra keyword arguments set on the Dispatcher
    (``dp["gateway"] = client``) are automatically passed to handler
    functions that declare a matching parameter name.  This helper
    exists mainly for backward-compatibility and explicit typing.
    """
    return gateway


async def _fetch_graphs(gateway: GatewayClient) -> list[dict]:
    """Fetch available graphs, return empty list on error."""
    try:
        return await gateway.get_graph_list()
    except Exception as exc:
        logger.warning("telegram.graphs_fetch_failed", error=str(exc))
        return []


def _format_graph_menu(graphs: list[dict]) -> tuple[str, dict[str, str | None]]:
    """Build the graph selection menu text and number→graph_id mapping.

    Returns:
        (menu_text, {number_str: graph_id_or_None})
    """
    lines = ["Каким графом выполнить задачу?\n"]
    mapping: dict[str, str | None] = {}

    for idx, g in enumerate(graphs, start=1):
        display = g.get("display_name", g.get("graph_id", "?"))
        desc = g.get("description", "")
        short_desc = (desc[:60] + "...") if len(desc) > 60 else desc
        lines.append(f"{idx}. {display} — {short_desc}")
        mapping[str(idx)] = g.get("graph_id") or g.get("name")

    # Last option: LLM auto-select
    auto_num = str(len(graphs) + 1)
    lines.append(f"{auto_num}. 🤖 Выбор сделает ЛЛМ (рекомендуется)")
    mapping[auto_num] = None  # None → graph_id not specified → Switch-Agent

    return "\n".join(lines), mapping


# ─────── Command handlers ──────────────────────────────────


@router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "👋 Привет! Я AI-crew бот.\n\n"
        "Команды:\n"
        "/task — создать задачу\n"
        "/status — статус текущей задачи\n"
        "/cancel — отменить создание задачи\n"
        "/help — список команд"
    )


@router.message(Command("help"))
async def cmd_help(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "📋 Доступные команды:\n\n"
        "/task — создать новую задачу для AI-команды\n"
        "/status — показать статус текущей задачи\n"
        "/cancel — отменить создание задачи\n"
        "/help — показать это сообщение"
    )


@router.message(Command("cancel"))
async def cmd_cancel(message: types.Message, state: FSMContext):
    current = await state.get_state()
    if current is None:
        await message.answer("Нет активного процесса для отмены.")
    else:
        await state.clear()
        await message.answer("❌ Создание задачи отменено.")


@router.message(Command("task"))
async def cmd_task(message: types.Message, state: FSMContext, gateway: GatewayClient):
    """Start the task creation dialog.

    If the user typed ``/task some text``, use it as the task description
    and go straight to graph selection.  Otherwise, ask for the task.
    """
    task_text = (message.text or "").replace("/task", "", 1).strip()

    if task_text:
        # Skip step 1 — go directly to graph selection
        await _show_graph_selection(message, state, task_text, gateway=gateway)
    else:
        await state.set_state(TaskCreation.waiting_for_task)
        await message.answer("📝 Введите описание задачи:")


# ─────── FSM step handlers ─────────────────────────────────


@router.message(TaskCreation.waiting_for_task)
async def on_task_text(message: types.Message, state: FSMContext, gateway: GatewayClient):
    """Step 1: User entered the task description."""
    task_text = (message.text or "").strip()
    if not task_text:
        await message.answer("❌ Описание задачи не может быть пустым. Попробуйте ещё раз:")
        return

    await _show_graph_selection(message, state, task_text, gateway=gateway)


async def _show_graph_selection(
    message: types.Message,
    state: FSMContext,
    task_text: str,
    gateway: GatewayClient | None = None,
):
    """Show graph selection menu and transition to waiting_for_graph state."""
    if gateway is None:
        raise RuntimeError("GatewayClient not injected via Dispatcher")
    graphs = await _fetch_graphs(gateway)

    if not graphs:
        # No graphs available (or fetch failed) → create task with auto-routing
        await _create_task(message, state, task_text, graph_id=None)
        return

    menu_text, mapping = _format_graph_menu(graphs)

    await state.update_data(task_text=task_text, graph_mapping=mapping)
    await state.set_state(TaskCreation.waiting_for_graph)
    await message.answer(menu_text)


@router.message(TaskCreation.waiting_for_graph)
async def on_graph_selection(message: types.Message, state: FSMContext, gateway: GatewayClient):
    """Step 2: User picked a graph number."""
    data = await state.get_data()
    task_text = data.get("task_text", "")
    mapping: dict[str, str | None] = data.get("graph_mapping", {})

    choice = (message.text or "").strip()

    if choice not in mapping:
        valid = ", ".join(sorted(mapping.keys(), key=int))
        await message.answer(f"❌ Неверный выбор. Введите номер ({valid}):")
        return

    graph_id = mapping[choice]
    await _create_task(message, state, task_text, graph_id=graph_id, gateway=gateway)


# ─────── Task creation ─────────────────────────────────────


async def _create_task(
    message: types.Message,
    state: FSMContext,
    task_text: str,
    graph_id: str | None,
    gateway: GatewayClient | None = None,
):
    """Create the task via Gateway and report back to the user."""
    await state.clear()  # Exit FSM

    if gateway is None:
        raise RuntimeError("GatewayClient not injected via Dispatcher")
    try:
        kwargs: dict = {}
        if graph_id is not None:
            kwargs["graph_id"] = graph_id

        result = await gateway.create_run(task=task_text, **kwargs)
        thread_id = result.get("thread_id", "unknown")
        chosen_graph = result.get("graph_id", "auto")
        _active_tasks[message.chat.id] = thread_id

        classification = result.get("classification")
        reasoning = ""
        if classification:
            reasoning = f"\n💡 Причина: {classification.get('reasoning', '')}"

        await message.answer(
            f"✅ Задача создана!\n\n"
            f"🔗 Thread: `{thread_id}`\n"
            f"📊 Граф: {chosen_graph}"
            f"{reasoning}\n\n"
            f"Используйте /status для отслеживания.",
            parse_mode="Markdown",
        )
        logger.info(
            "telegram.task_created",
            chat_id=message.chat.id,
            thread_id=thread_id,
            graph_id=chosen_graph,
        )
    except Exception as exc:
        logger.error("telegram.task_error", error=str(exc))
        await message.answer(f"❌ Ошибка: {exc}")


# ─────── Status & HITL ─────────────────────────────────────


@router.message(Command("status"))
async def cmd_status(message: types.Message, state: FSMContext, gateway: GatewayClient):
    await state.clear()  # In case user is in the middle of task creation
    thread_id = _active_tasks.get(message.chat.id)
    if not thread_id:
        await message.answer("❌ Нет активной задачи. Создайте через /task")
        return
    try:
        thread_state = await gateway.get_thread_state(thread_id)
        values = thread_state.get("values", thread_state)
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
async def handle_message(message: types.Message, state: FSMContext, gateway: GatewayClient):
    """Handle free-text messages as HITL clarification responses."""
    thread_id = _active_tasks.get(message.chat.id)
    if not thread_id:
        await message.answer("💡 Используйте /task для создания задачи или /help для списка команд.")
        return
    try:
        thread_state = await gateway.get_thread_state(thread_id)
        values = thread_state.get("values", thread_state)
        if values.get("needs_clarification"):
            await gateway.send_clarification(thread_id, message.text)
            await message.answer("✅ Ответ отправлен. Агенты продолжают работу...")
            logger.info("telegram.clarification_sent", chat_id=message.chat.id)
        else:
            await message.answer("ℹ️ Нет активного вопроса. Используйте /status для проверки.")
    except Exception as exc:
        logger.error("telegram.message_error", error=str(exc))
        await message.answer(f"❌ Ошибка: {exc}")
