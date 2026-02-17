"""
WebApp Deploy Test Graph
========================

Fast smoke-to-deploy flow for web applications.

Flow::

    START -> Developer -> QA -(pass)-> DevOps -> git_commit -> deploy_trigger
                      \-(fail, once)-> Developer
        deploy_trigger -(success)-> deploy_verify -> report -> END
        deploy_trigger -(other)-> report -> END
"""

import time as _time
from typing import Literal

import structlog
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from webapp_deploy_test.state import WebAppDeployTestState
from common.logging import configure_logging
from common.git import make_git_commit_node

from dev_team.agents.developer import developer_agent as _developer_agent
from dev_team.agents.qa import qa_agent as _qa_agent
from dev_team.agents.devops import devops_agent as _devops_agent
from dev_team.graph import deploy_trigger_node, deploy_verify_node

configure_logging()
logger = structlog.get_logger()

MAX_QA_RETRIES = 1

DEFAULT_WEBAPP_TASK = (
    "Сделай минимальное рабочее веб-приложение, готовое к быстрому деплою.\n"
    "Критерии:\n"
    "1) Приложение должно запускаться локально и отдавать HTTP 200 на GET /health.\n"
    "2) Добавь минимальные тесты для smoke-проверки.\n"
    "3) Учитывай deploy-ready структуру (Dockerfile/CI могут быть добавлены DevOps-узлом).\n"
    "4) Не добавляй лишние файлы-шаблоны и псевдофайлы generated_file_*.txt.\n"
)


def developer_node(state: WebAppDeployTestState, config=None) -> dict:
    """Generate web app code or fix QA issues."""
    t0 = _time.monotonic()
    user_task = (state.get("task") or "").strip()
    effective_task = (
        f"{DEFAULT_WEBAPP_TASK}\n\nДополнительный запрос пользователя:\n{user_task}"
        if user_task
        else DEFAULT_WEBAPP_TASK
    )

    logger.info(
        "webapp_deploy_test.developer.enter",
        task_len=len(effective_task),
        qa_retry_count=state.get("qa_retry_count", 0),
    )
    result = _developer_agent(
        {
            **state,
            "task": effective_task,
            "issues_found": state.get("issues_found", []),
        },
        config=config,
    )
    elapsed_ms = (_time.monotonic() - t0) * 1000

    tech_stack = result.get("tech_stack") or state.get("tech_stack") or []
    if not tech_stack:
        tech_stack = ["python", "fastapi"]

    logger.info(
        "webapp_deploy_test.developer.exit",
        elapsed_ms=round(elapsed_ms),
        files=len(result.get("code_files", [])),
    )
    return {
        **result,
        "task": effective_task,
        "tech_stack": tech_stack,
        "current_agent": "developer",
    }


def qa_node(state: WebAppDeployTestState, config=None) -> dict:
    """Run QA sandbox/browser checks."""
    t0 = _time.monotonic()
    logger.info(
        "webapp_deploy_test.qa.enter",
        files=len(state.get("code_files", [])),
        retry=state.get("qa_retry_count", 0),
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
        "webapp_deploy_test.qa.exit",
        elapsed_ms=round(elapsed_ms),
        approved=result.get("test_results", {}).get("approved"),
        issues=len(result.get("issues_found", [])),
    )
    return {
        **result,
        "current_agent": "qa",
    }


def route_after_qa(state: WebAppDeployTestState) -> Literal["developer", "devops"]:
    """Fast QA gate: one retry max, then continue to deploy path."""
    test_results = state.get("test_results", {}) or {}
    if test_results.get("approved", False):
        logger.info("webapp_deploy_test.route_after_qa", decision="devops", reason="approved")
        return "devops"

    retries = state.get("qa_retry_count", 0)
    if retries < MAX_QA_RETRIES:
        logger.info(
            "webapp_deploy_test.route_after_qa",
            decision="developer",
            reason="retry_once",
            qa_retry_count=retries,
        )
        return "developer"

    logger.warning(
        "webapp_deploy_test.route_after_qa",
        decision="devops",
        reason="retry_limit_reached",
        qa_retry_count=retries,
    )
    return "devops"


def bump_qa_retry_node(state: WebAppDeployTestState) -> dict:
    """Increment QA retry counter when looping back to developer."""
    return {
        "qa_retry_count": state.get("qa_retry_count", 0) + 1,
        "current_agent": "qa_retry",
    }


def devops_node(state: WebAppDeployTestState, config=None) -> dict:
    """Generate deploy infrastructure and deploy metadata."""
    t0 = _time.monotonic()
    logger.info(
        "webapp_deploy_test.devops.enter",
        files=len(state.get("code_files", [])),
        tech_stack=state.get("tech_stack", [])[:5],
    )
    result = _devops_agent(state, config=config)
    elapsed_ms = (_time.monotonic() - t0) * 1000
    logger.info(
        "webapp_deploy_test.devops.exit",
        elapsed_ms=round(elapsed_ms),
        infra_files=len(result.get("infra_files", [])),
        deploy_repo=bool(result.get("deploy_repo")),
        deploy_url=bool(result.get("deploy_url")),
    )
    return {
        **result,
        "current_agent": "devops",
    }


def route_after_deploy_trigger(
    state: WebAppDeployTestState,
) -> Literal["deploy_verify", "report"]:
    """Fast deploy router: do not loop back to developer on CI failure."""
    ci_status = state.get("ci_status", "")
    if ci_status == "success":
        logger.info("webapp_deploy_test.route_after_deploy", decision="deploy_verify", ci_status=ci_status)
        return "deploy_verify"

    logger.info("webapp_deploy_test.route_after_deploy", decision="report", ci_status=ci_status)
    return "report"


def report_node(state: WebAppDeployTestState) -> dict:
    """Build final lightweight report."""
    qa_approved = bool((state.get("test_results") or {}).get("approved"))
    ci_status = state.get("ci_status", "not_run")
    deploy_status = state.get("deploy_status", "unknown")
    pr_url = state.get("pr_url", "")
    deploy_url = state.get("deploy_url", "")
    qa_retry_count = state.get("qa_retry_count", 0)

    lines = [
        "WebApp Deploy Test Report",
        f"QA approved: {qa_approved}",
        f"QA retries used: {qa_retry_count}",
        f"CI status: {ci_status}",
        f"Deploy status: {deploy_status}",
    ]
    if pr_url:
        lines.append(f"PR: {pr_url}")
    if deploy_url:
        lines.append(f"Deploy URL: {deploy_url}")

    if not qa_approved:
        lines.append("Warning: deploy flow continued after QA retry limit for faster pipeline validation.")

    summary = "\n".join(lines)
    return {
        "deploy_report": summary,
        "summary": summary,
        "current_agent": "complete",
    }


git_commit_node = make_git_commit_node("webapp_deploy_test")


def create_graph() -> StateGraph:
    """Create fast web-app deploy test graph."""
    logger.info("webapp_deploy_test.graph.create")
    builder = StateGraph(WebAppDeployTestState)

    builder.add_node("developer", developer_node)
    builder.add_node("qa", qa_node)
    builder.add_node("qa_retry", bump_qa_retry_node)
    builder.add_node("devops", devops_node)
    builder.add_node("git_commit", git_commit_node)
    builder.add_node("deploy_trigger", deploy_trigger_node)
    builder.add_node("deploy_verify", deploy_verify_node)
    builder.add_node("report", report_node)

    builder.add_edge(START, "developer")
    builder.add_edge("developer", "qa")

    builder.add_conditional_edges(
        "qa",
        route_after_qa,
        {
            "developer": "qa_retry",
            "devops": "devops",
        },
    )
    builder.add_edge("qa_retry", "developer")

    builder.add_edge("devops", "git_commit")
    builder.add_edge("git_commit", "deploy_trigger")

    builder.add_conditional_edges(
        "deploy_trigger",
        route_after_deploy_trigger,
        {
            "deploy_verify": "deploy_verify",
            "report": "report",
        },
    )
    builder.add_edge("deploy_verify", "report")
    builder.add_edge("report", END)

    return builder


checkpointer = MemorySaver()
graph = create_graph().compile(checkpointer=checkpointer)
logger.info("webapp_deploy_test.graph.compiled")

__all__ = ["graph", "WebAppDeployTestState"]
