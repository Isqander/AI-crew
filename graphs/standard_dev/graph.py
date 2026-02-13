"""
Standard Dev Graph
==================

Medium-complexity autonomous development workflow.

Flow::

    START ─► PM ─► Developer ─► QA ─┬─► git_commit ─► END
                       ▲             │
                       └── (issues) ─┘
                        (max 2 iterations)

No HITL — fully autonomous.  After 2 QA iterations the code is
committed regardless (with a note about remaining issues).
"""

import os
import time as _time
from typing import Literal

import structlog
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from standard_dev.state import StandardDevState

# Reuse agents from dev_team
from dev_team.agents.pm import pm_agent as _pm_agent
from dev_team.agents.developer import developer_agent as _dev_agent
from dev_team.agents.qa import qa_agent as _qa_agent
from dev_team.tools.git_workspace import commit_and_create_pr
from dev_team.logging_config import configure_logging

configure_logging()
logger = structlog.get_logger()

MAX_QA_ITERATIONS = 2


def _build_code_summary(code_files: list, task: str) -> str:
    """Format generated code files into a readable summary."""
    if not code_files:
        return f"Task completed: {task}\nNo code files were generated."
    parts = [f"Task completed: {task}", f"{len(code_files)} file(s) generated:\n"]
    for cf in code_files:
        path = cf.get("path", "unknown")
        lang = cf.get("language", "")
        content = cf.get("content", "")
        parts.append(f"### {path}")
        parts.append(f"```{lang}\n{content}\n```\n")
    return "\n".join(parts)


# ────────────────────── Node functions ──────────────────────


def pm_node(state: StandardDevState, config=None) -> dict:
    """PM decomposes the task."""
    t0 = _time.monotonic()
    logger.info("standard_dev.pm.enter", task_len=len(state.get("task", "")))
    result = _pm_agent(state, config=config)
    elapsed_ms = (_time.monotonic() - t0) * 1000
    logger.info("standard_dev.pm.exit", elapsed_ms=round(elapsed_ms))
    return result


def developer_node(state: StandardDevState, config=None) -> dict:
    """Developer writes or fixes code."""
    t0 = _time.monotonic()
    qa_iter = state.get("qa_iteration_count", 0)
    logger.info("standard_dev.developer.enter", qa_iteration=qa_iter,
                issues_count=len(state.get("issues_found", [])))
    result = _dev_agent(state, config=config)
    elapsed_ms = (_time.monotonic() - t0) * 1000
    logger.info("standard_dev.developer.exit", elapsed_ms=round(elapsed_ms),
                code_files=len(result.get("code_files", [])))
    return result


def qa_node(state: StandardDevState, config=None) -> dict:
    """QA reviews the code."""
    t0 = _time.monotonic()
    logger.info("standard_dev.qa.enter", code_files=len(state.get("code_files", [])),
                qa_iteration=state.get("qa_iteration_count", 0))
    result = _qa_agent(state, config=config)
    elapsed_ms = (_time.monotonic() - t0) * 1000
    logger.info("standard_dev.qa.exit", elapsed_ms=round(elapsed_ms),
                issues_found=len(result.get("issues_found", [])),
                approved=result.get("test_results", {}).get("approved", False))
    return result


def git_commit_node(state: StandardDevState) -> dict:
    """Commit code and create PR."""
    t0 = _time.monotonic()
    code_files = state.get("code_files", [])
    repository = state.get("repository") or os.getenv("GITHUB_DEFAULT_REPO", "")
    task = state.get("task", "AI-generated task")
    github_token_set = bool(os.getenv("GITHUB_TOKEN"))
    logger.info("standard_dev.git_commit.enter", repository=repository or "none",
                files=len(code_files), github_token_set=github_token_set)

    if not repository:
        elapsed_ms = (_time.monotonic() - t0) * 1000
        logger.warning("standard_dev.git_commit.skip", reason="no_repository",
                       elapsed_ms=round(elapsed_ms))
        return {
            "summary": _build_code_summary(code_files, task),
            "current_agent": "complete",
        }

    logger.info("standard_dev.git_commit.committing", repository=repository, files=len(code_files))
    result = commit_and_create_pr(repo_name=repository, task=task, code_files=code_files)
    elapsed_ms = (_time.monotonic() - t0) * 1000

    if result.get("error") and result["files_committed"] == 0:
        logger.error("standard_dev.git_commit.failed", error=result["error"],
                     elapsed_ms=round(elapsed_ms))
        return {
            "summary": f"⚠️ Git failed: {result['error']}\n\n{_build_code_summary(code_files, task)}",
            "current_agent": "complete",
            "error": result["error"],
        }

    logger.info("standard_dev.git_commit.success", pr_url=result.get("pr_url", ""),
                branch=result.get("working_branch", ""),
                files_committed=result.get("files_committed", 0),
                elapsed_ms=round(elapsed_ms))
    return {
        "pr_url": result.get("pr_url", ""),
        "commit_sha": result.get("commit_sha", ""),
        "working_branch": result.get("working_branch", ""),
        "working_repo": repository,
        "summary": (
            f"✅ Created PR with {result['files_committed']} file(s) on {repository}\n"
            f"Branch: {result.get('working_branch', '')}\n"
            f"PR: {result.get('pr_url', '')}"
        ),
        "current_agent": "complete",
    }


# ────────────────────── Routing ─────────────────────────────


def route_after_qa(state: StandardDevState) -> Literal["developer", "git_commit"]:
    """Route after QA: fix issues or commit.

    No HITL — after MAX_QA_ITERATIONS, commit regardless.
    """
    qa_iter = state.get("qa_iteration_count", 0)

    if state.get("issues_found") and qa_iter < MAX_QA_ITERATIONS:
        logger.debug("standard_dev.route_qa", decision="developer", qa_iter=qa_iter)
        return "developer"

    # Approved or max iterations reached — commit
    if qa_iter >= MAX_QA_ITERATIONS and state.get("issues_found"):
        logger.info("standard_dev.route_qa", decision="git_commit", reason="max_iterations", qa_iter=qa_iter)
    else:
        logger.debug("standard_dev.route_qa", decision="git_commit", approved=True)
    return "git_commit"


# ────────────────────── Graph definition ────────────────────


def create_graph() -> StateGraph:
    """Create the standard dev graph: PM → Developer → QA → git_commit."""
    logger.info("standard_dev.graph.create")
    builder = StateGraph(StandardDevState)

    builder.add_node("pm", pm_node)
    builder.add_node("developer", developer_node)
    builder.add_node("qa", qa_node)
    builder.add_node("git_commit", git_commit_node)

    # Edges
    builder.add_edge(START, "pm")
    builder.add_edge("pm", "developer")
    builder.add_edge("developer", "qa")

    builder.add_conditional_edges(
        "qa",
        route_after_qa,
        {
            "developer": "developer",
            "git_commit": "git_commit",
        },
    )

    builder.add_edge("git_commit", END)

    return builder


# Compile (no interrupt_before — no HITL)
checkpointer = MemorySaver()
graph = create_graph().compile(checkpointer=checkpointer)
logger.info("standard_dev.graph.compiled")

__all__ = ["graph", "StandardDevState"]
