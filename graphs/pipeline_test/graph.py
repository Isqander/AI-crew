"""
Pipeline Test Graph
===================

Full pipeline validation: Developer → Lint (loop) → QA → Report.

Tests:
  1. Developer generates code (with .qa-hints.yaml)
  2. Lint check runs in sandbox (ruff/eslint)
  3. Dev↔Lint fix loop (up to 3 iterations)
  4. QA sandbox tests (pytest / jest)
  5. QA visual exploration (Playwright)
  6. Report with all results

Flow::

    START → Developer → lint_check ─(clean)─→ QA → Report → END
                ↑           │
                └──(issues)─┘  (max 3 iterations)
"""

import time as _time
from typing import Literal

import structlog
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from pipeline_test.state import PipelineTestState
from dev_team.agents.developer import developer_agent as _developer_agent
from dev_team.agents.qa import qa_agent as _qa_agent
from dev_team.graph import lint_check_node as _lint_check_node, _detect_language
from common.logging import configure_logging

configure_logging()
logger = structlog.get_logger()

MAX_LINT_ITERATIONS = 3


# ── Developer node ──────────────────────────────────────────────────


def developer_node(state: PipelineTestState, config=None) -> dict:
    """Generate code or fix lint issues using the Developer agent."""
    t0 = _time.monotonic()
    user_task = (state.get("task") or "").strip()

    lint_status = state.get("lint_status", "")

    logger.info(
        "pipeline_test.developer.enter",
        task_len=len(user_task),
        lint_status=lint_status,
    )

    # Build state for the developer agent
    dev_state = {
        **state,
        "task": user_task,
        "issues_found": state.get("issues_found", []),
    }

    # If lint issues — set lint_status so developer routes to fix_lint
    if lint_status == "issues":
        dev_state["lint_status"] = "issues"
        dev_state["lint_log"] = state.get("lint_log", "")

    result = _developer_agent(dev_state, config=config)
    elapsed_ms = (_time.monotonic() - t0) * 1000

    tech_stack = result.get("tech_stack") or state.get("tech_stack") or []
    if not tech_stack:
        tech_stack = ["html", "css", "javascript"]

    logger.info(
        "pipeline_test.developer.exit",
        elapsed_ms=round(elapsed_ms),
        files=len(result.get("code_files", [])),
        action="fix_lint" if lint_status == "issues" else "implement",
    )

    return {
        **result,
        "tech_stack": tech_stack,
        "current_agent": "developer",
    }


# ── Lint check node ────────────────────────────────────────────────


def lint_node(state: PipelineTestState, config=None) -> dict:
    """Run linter in sandbox on generated code."""
    t0 = _time.monotonic()
    logger.info(
        "pipeline_test.lint.enter",
        files=len(state.get("code_files", [])),
        lint_iteration=state.get("lint_iteration_count", 0),
    )

    result = _lint_check_node(state, config=config)
    elapsed_ms = (_time.monotonic() - t0) * 1000

    logger.info(
        "pipeline_test.lint.exit",
        elapsed_ms=round(elapsed_ms),
        lint_status=result.get("lint_status"),
        lint_iteration=result.get("lint_iteration_count"),
    )
    return result


def route_after_lint(
    state: PipelineTestState,
) -> Literal["developer", "qa"]:
    """Route after lint: clean → QA, issues → developer (fix loop)."""
    lint_status = state.get("lint_status", "")
    lint_iter = state.get("lint_iteration_count", 0)

    if lint_status in ("clean", "skipped", "error"):
        logger.info("pipeline_test.route_lint", decision="qa", lint_status=lint_status)
        return "qa"

    if lint_iter >= MAX_LINT_ITERATIONS:
        logger.warning(
            "pipeline_test.route_lint",
            decision="qa",
            lint_status=lint_status,
            lint_iter=lint_iter,
            reason="max_lint_iterations",
        )
        return "qa"

    logger.info(
        "pipeline_test.route_lint",
        decision="developer",
        lint_status=lint_status,
        lint_iter=lint_iter,
    )
    return "developer"


# ── QA node ─────────────────────────────────────────────────────────


def qa_node(state: PipelineTestState, config=None) -> dict:
    """Run QA sandbox + visual checks."""
    t0 = _time.monotonic()
    logger.info(
        "pipeline_test.qa.enter",
        files=len(state.get("code_files", [])),
        tech_stack=state.get("tech_stack", [])[:5],
    )

    result = _qa_agent(
        {
            **state,
            "review_iteration_count": 0,
            "issues_found": state.get("issues_found", []),
        },
        config=config,
    )
    elapsed_ms = (_time.monotonic() - t0) * 1000

    logger.info(
        "pipeline_test.qa.exit",
        elapsed_ms=round(elapsed_ms),
        approved=result.get("test_results", {}).get("approved"),
        issues=len(result.get("issues_found", [])),
    )
    return {
        **result,
        "current_agent": "qa",
    }


# ── Report node ─────────────────────────────────────────────────────


def _build_report(state: PipelineTestState) -> str:
    """Build a comprehensive pipeline test report."""
    lint_status = state.get("lint_status", "not_run")
    lint_log = state.get("lint_log", "")
    lint_iter = state.get("lint_iteration_count", 0)

    sandbox = state.get("sandbox_results") or {}
    browser = state.get("browser_test_results") or {}
    test_results = state.get("test_results") or {}
    issues = state.get("issues_found", [])

    sections: list[str] = []

    # ── Verdict ──
    verdict = "PASS" if test_results.get("approved") else "FAIL"
    sections.append(f"Итоговый вердикт: {verdict}")

    # ── Lint section ──
    sections.append("")
    sections.append("═══ LINT CHECK ═══")
    sections.append(f"Статус: {lint_status}")
    sections.append(f"Итерации Dev↔Lint: {lint_iter}")
    if lint_status == "clean":
        sections.append("Результат: Код прошёл проверку линтером ✓")
    elif lint_status == "issues":
        sections.append(f"Результат: Lint issues остались после {lint_iter} попыток фикса")
    elif lint_status == "error":
        sections.append("Результат: Ошибка запуска линтера (sandbox недоступен?)")
    elif lint_status == "skipped":
        sections.append("Результат: Lint пропущен (нет файлов)")
    if lint_log and lint_status == "issues":
        sections.append(f"Лог:\n{lint_log[:1000]}")

    # ── Sandbox section ──
    sections.append("")
    sections.append("═══ SANDBOX TESTS ═══")
    if sandbox:
        sections.append(
            f"exit_code={sandbox.get('exit_code', 'n/a')}, "
            f"tests_passed={sandbox.get('tests_passed', 'n/a')}, "
            f"duration={sandbox.get('duration_seconds', 'n/a')}s"
        )
    else:
        sections.append("Sandbox не запущен (нет sandbox_results)")

    # ── Visual QA section ──
    sections.append("")
    sections.append("═══ VISUAL QA ═══")
    if browser:
        status = browser.get("test_status", "not_run")
        screenshots = browser.get("screenshots", []) or []
        names = [s.get("name", "") for s in screenshots if s.get("name")]
        sections.append(f"Статус: {status}")
        sections.append(f"Скриншоты: {len(names)}")
        if names:
            sections.append(f"Файлы: {', '.join(names[:10])}")
        steps_ok = browser.get("successful_steps", 0)
        steps_fail = browser.get("failed_steps", 0)
        sections.append(f"Шаги: {steps_ok} OK / {steps_fail} FAIL")
    else:
        sections.append("Visual QA не выполнен")

    # ── Issues ──
    sections.append("")
    sections.append("═══ ПРОБЛЕМЫ ═══")
    if issues:
        for item in issues:
            sections.append(f"- {item}")
    else:
        sections.append("- Нет явных проблем")

    return "\n".join(sections)


def report_node(state: PipelineTestState) -> dict:
    """Build final pipeline report."""
    t0 = _time.monotonic()
    report = _build_report(state)
    elapsed_ms = (_time.monotonic() - t0) * 1000
    logger.info(
        "pipeline_test.report.done",
        elapsed_ms=round(elapsed_ms),
        report_len=len(report),
    )
    return {
        "pipeline_report": report,
        "summary": report,
        "current_agent": "complete",
    }


# ── Graph creation ──────────────────────────────────────────────────


def create_graph() -> StateGraph:
    """Create pipeline test graph: Developer → Lint (loop) → QA → Report."""
    logger.info("pipeline_test.graph.create")
    builder = StateGraph(PipelineTestState)

    builder.add_node("developer", developer_node)
    builder.add_node("lint_check", lint_node)
    builder.add_node("qa", qa_node)
    builder.add_node("report", report_node)

    # START → Developer
    builder.add_edge(START, "developer")

    # Developer → Lint
    builder.add_edge("developer", "lint_check")

    # Lint → (QA | Developer)
    builder.add_conditional_edges(
        "lint_check",
        route_after_lint,
        {
            "qa": "qa",
            "developer": "developer",
        }
    )

    # QA → Report
    builder.add_edge("qa", "report")

    # Report → END
    builder.add_edge("report", END)

    return builder


checkpointer = MemorySaver()
graph = create_graph().compile(checkpointer=checkpointer)
logger.info("pipeline_test.graph.compiled")

__all__ = ["graph", "PipelineTestState"]
