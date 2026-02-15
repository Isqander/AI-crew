"""
QA Agent Test Graph
===================

Focused flow for validating QA agent runtime + visual checks.

Flow:
    START -> Developer -> QA -> Report -> END
"""

import time as _time

import structlog
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from qa_agent_test.state import QAAgentTestState
from dev_team.agents.developer import developer_agent as _developer_agent
from dev_team.agents.qa import qa_agent as _qa_agent
from dev_team.logging_config import configure_logging

configure_logging()
logger = structlog.get_logger()

DEFAULT_WEB_APP_TASK = (
    "Создай веб-приложение с UI для проверки QA.\n"
    "Требования:\n"
    "1) Стек: Node.js + Express для сервера, HTML + CSS + vanilla JavaScript для фронта.\n"
    "2) Обязательно создай package.json с зависимостями (express).\n"
    "3) Файлы: package.json, server.js, public/index.html, public/styles.css, public/app.js.\n"
    "4) UI: заголовок, текстовое поле, кнопка, блок результата.\n"
    "5) Поведение: по кнопке выводить текст из поля в блок результата.\n"
    "6) Сервер должен отдавать статику из папки public/ на порту 3000.\n"
    "7) Добавь тест: tests/app.test.js (jest) — проверка что сервер отвечает 200 на GET /."
)


def developer_node(state: QAAgentTestState, config=None) -> dict:
    """Generate a minimal web app using the existing developer agent."""
    t0 = _time.monotonic()
    user_task = (state.get("task") or "").strip()
    effective_task = (
        f"{DEFAULT_WEB_APP_TASK}\n\nДополнительный запрос пользователя:\n{user_task}"
        if user_task
        else DEFAULT_WEB_APP_TASK
    )

    logger.info("qa_agent_test.developer.enter", task_len=len(effective_task))
    result = _developer_agent(
        {
            **state,
            "task": effective_task,
            "issues_found": [],
        },
        config=config,
    )
    elapsed_ms = (_time.monotonic() - t0) * 1000

    # Ensure UI testing is attempted in QA node.
    tech_stack = result.get("tech_stack") or []
    if not tech_stack:
        tech_stack = ["html", "css", "javascript"]

    logger.info(
        "qa_agent_test.developer.exit",
        elapsed_ms=round(elapsed_ms),
        files=len(result.get("code_files", [])),
    )
    return {
        **result,
        "task": effective_task,
        "tech_stack": tech_stack,
        "current_agent": "developer",
        "next_agent": "qa",
    }


def qa_node(state: QAAgentTestState, config=None) -> dict:
    """Run QA sandbox + visual checks via existing QA agent."""
    t0 = _time.monotonic()
    logger.info(
        "qa_agent_test.qa.enter",
        files=len(state.get("code_files", [])),
        tech_stack=state.get("tech_stack", [])[:5],
    )

    result = _qa_agent(
        {
            **state,
            "review_iteration_count": state.get("review_iteration_count", 0),
            "issues_found": state.get("issues_found", []),
        },
        config=config,
    )
    elapsed_ms = (_time.monotonic() - t0) * 1000
    logger.info(
        "qa_agent_test.qa.exit",
        elapsed_ms=round(elapsed_ms),
        approved=result.get("test_results", {}).get("approved"),
        issues=len(result.get("issues_found", [])),
    )
    return {
        **result,
        "current_agent": "qa",
        "next_agent": "report",
    }


def _build_qa_report(state: QAAgentTestState) -> str:
    sandbox = state.get("sandbox_results") or {}
    browser = state.get("browser_test_results") or {}
    test_results = state.get("test_results") or {}
    issues = state.get("issues_found", [])

    sandbox_checked = bool(sandbox)
    browser_checked = bool(browser)

    sandbox_exit = sandbox.get("exit_code", "n/a")
    tests_passed = sandbox.get("tests_passed", "n/a")
    sandbox_duration = sandbox.get("duration_seconds", "n/a")

    browser_status = browser.get("test_status", "not_run")
    screenshots = browser.get("screenshots", []) or []
    screenshot_names = [s.get("name", "") for s in screenshots if s.get("name")]
    console_logs = browser.get("console_logs", "")
    network_errors = browser.get("network_errors", []) or []

    checked_ok: list[str] = []
    checked_fail: list[str] = []

    if sandbox_checked:
        checked_ok.append(
            f"Sandbox-запуск выполнен (exit_code={sandbox_exit}, tests_passed={tests_passed}, duration={sandbox_duration}s)"
        )
    else:
        checked_fail.append("Sandbox-запуск не выполнен (нет sandbox_results)")

    if browser_checked:
        checked_ok.append(
            f"Визуальная QA-проверка выполнена (status={browser_status}, screenshots={len(screenshot_names)})"
        )
        if screenshot_names:
            checked_ok.append(f"Сделаны скриншоты: {', '.join(screenshot_names[:10])}")
        else:
            checked_fail.append("Визуальная часть запущена, но скриншоты не получены")
    else:
        checked_fail.append("Визуальная QA-проверка не выполнена (нет browser_test_results)")

    if network_errors:
        checked_fail.append(f"Network errors: {len(network_errors)}")
    if browser_checked and browser_status != "pass":
        checked_fail.append(f"Визуальный тест завершился со статусом: {browser_status}")
    if console_logs:
        checked_ok.append("Собраны browser console logs")

    verdict = "PASS" if test_results.get("approved") else "FAIL"
    issues_text = "\n".join(f"- {item}" for item in issues) if issues else "- Нет явных проблем по мнению QA"
    ok_text = "\n".join(f"- {item}" for item in checked_ok) if checked_ok else "- Нет"
    fail_text = "\n".join(f"- {item}" for item in checked_fail) if checked_fail else "- Нет"

    return (
        "Отчёт QA-агента (sandbox + visual)\n"
        f"Итоговый вердикт: {verdict}\n\n"
        "Что QA смог проверить:\n"
        f"{ok_text}\n\n"
        "Что QA не смог проверить / где есть ограничения:\n"
        f"{fail_text}\n\n"
        "Найденные проблемы:\n"
        f"{issues_text}"
    )


def report_node(state: QAAgentTestState) -> dict:
    """Build final textual report for QA agent test run."""
    t0 = _time.monotonic()
    report = _build_qa_report(state)
    elapsed_ms = (_time.monotonic() - t0) * 1000
    logger.info("qa_agent_test.report.done", elapsed_ms=round(elapsed_ms), report_len=len(report))
    return {
        "qa_report": report,
        "summary": report,
        "current_agent": "complete",
    }


def create_graph() -> StateGraph:
    """Create QA agent test graph."""
    logger.info("qa_agent_test.graph.create")
    builder = StateGraph(QAAgentTestState)

    builder.add_node("developer", developer_node)
    builder.add_node("qa", qa_node)
    builder.add_node("report", report_node)

    builder.add_edge(START, "developer")
    builder.add_edge("developer", "qa")
    builder.add_edge("qa", "report")
    builder.add_edge("report", END)

    return builder


checkpointer = MemorySaver()
graph = create_graph().compile(checkpointer=checkpointer)
logger.info("qa_agent_test.graph.compiled")

__all__ = ["graph", "QAAgentTestState"]

