"""
Simple Dev Graph
================

Minimal development graph for quick, simple tasks.

Flow::

    START ─► Developer ─► git_commit ─► END

No HITL, no QA loop, no planning phase.
Single Developer agent writes code and commits directly.
"""

import os
import time as _time

import structlog
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from simple_dev.state import SimpleDevState

# Reuse the developer agent from dev_team
from dev_team.agents.developer import developer_agent as _dev_agent
from dev_team.tools.git_workspace import commit_and_create_pr
from dev_team.logging_config import configure_logging

configure_logging()
logger = structlog.get_logger()


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


def developer_node(state: SimpleDevState, config=None) -> dict:
    """Developer writes code.

    Reuses the DeveloperAgent from dev_team. The agent works with
    dict state via .get(), so it's compatible with SimpleDevState.
    """
    t0 = _time.monotonic()
    logger.info("simple_dev.developer.enter", task_len=len(state.get("task", "")))
    result = _dev_agent(state, config=config)
    elapsed_ms = (_time.monotonic() - t0) * 1000
    logger.info("simple_dev.developer.exit", elapsed_ms=round(elapsed_ms),
                code_files=len(result.get("code_files", [])))
    return result


def git_commit_node(state: SimpleDevState) -> dict:
    """Commit code and create PR (or return code in summary)."""
    t0 = _time.monotonic()
    code_files = state.get("code_files", [])
    repository = state.get("repository") or os.getenv("GITHUB_DEFAULT_REPO", "")
    task = state.get("task", "AI-generated task")
    github_token_set = bool(os.getenv("GITHUB_TOKEN"))
    logger.info("simple_dev.git_commit.enter", repository=repository or "none",
                files=len(code_files), github_token_set=github_token_set)

    if not repository:
        elapsed_ms = (_time.monotonic() - t0) * 1000
        logger.warning("simple_dev.git_commit.skip", reason="no_repository",
                       elapsed_ms=round(elapsed_ms))
        return {
            "summary": _build_code_summary(code_files, task),
            "current_agent": "complete",
        }

    logger.info("simple_dev.git_commit.committing", repository=repository, files=len(code_files))
    result = commit_and_create_pr(repo_name=repository, task=task, code_files=code_files)
    elapsed_ms = (_time.monotonic() - t0) * 1000

    if result.get("error") and result["files_committed"] == 0:
        logger.error("simple_dev.git_commit.failed", error=result["error"],
                     elapsed_ms=round(elapsed_ms))
        return {
            "summary": f"⚠️ Git failed: {result['error']}\n\n{_build_code_summary(code_files, task)}",
            "current_agent": "complete",
            "error": result["error"],
        }

    logger.info("simple_dev.git_commit.success", pr_url=result.get("pr_url", ""),
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


# ────────────────────── Graph definition ────────────────────


def create_graph() -> StateGraph:
    """Create the simple dev graph: Developer → git_commit → END."""
    logger.info("simple_dev.graph.create")
    builder = StateGraph(SimpleDevState)

    builder.add_node("developer", developer_node)
    builder.add_node("git_commit", git_commit_node)

    builder.add_edge(START, "developer")
    builder.add_edge("developer", "git_commit")
    builder.add_edge("git_commit", END)

    return builder


# Compile
checkpointer = MemorySaver()
graph = create_graph().compile(checkpointer=checkpointer)
logger.info("simple_dev.graph.compiled")

__all__ = ["graph", "SimpleDevState"]
