"""
Standard Dev Graph
==================

Medium-complexity autonomous development workflow.

Flow::

    START -> PM -> Developer -> Reviewer -+-> git_commit -> END
                       ^                  |
                       +-- (issues) ------+
                        (max 2 iterations)

No HITL -- fully autonomous.  After 2 Reviewer iterations the code is
committed regardless (with a note about remaining issues).
"""

import time as _time
from typing import Literal

import structlog
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from standard_dev.state import StandardDevState
from common.logging import configure_logging
from common.git import make_git_commit_node

# Reuse agents from dev_team
from dev_team.agents.pm import pm_agent as _pm_agent
from dev_team.agents.developer import developer_agent as _dev_agent
from dev_team.agents.reviewer import reviewer_agent as _reviewer_agent

configure_logging()
logger = structlog.get_logger()

MAX_REVIEW_ITERATIONS = 2


# ---------------------- Node functions ----------------------


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
    review_iter = state.get("review_iteration_count", 0)
    logger.info("standard_dev.developer.enter", review_iteration=review_iter,
                issues_count=len(state.get("issues_found", [])))
    result = _dev_agent(state, config=config)
    elapsed_ms = (_time.monotonic() - t0) * 1000
    logger.info("standard_dev.developer.exit", elapsed_ms=round(elapsed_ms),
                code_files=len(result.get("code_files", [])))
    return result


def reviewer_node(state: StandardDevState, config=None) -> dict:
    """Reviewer reviews the code."""
    t0 = _time.monotonic()
    logger.info("standard_dev.reviewer.enter", code_files=len(state.get("code_files", [])),
                review_iteration=state.get("review_iteration_count", 0))
    result = _reviewer_agent(state, config=config)
    elapsed_ms = (_time.monotonic() - t0) * 1000
    logger.info("standard_dev.reviewer.exit", elapsed_ms=round(elapsed_ms),
                issues_found=len(result.get("issues_found", [])),
                approved=result.get("test_results", {}).get("approved", False))
    return result


# git_commit_node created by shared factory from common.git
git_commit_node = make_git_commit_node("standard_dev")


# ---------------------- Routing ----------------------------


def route_after_reviewer(state: StandardDevState) -> Literal["developer", "git_commit"]:
    """Route after Reviewer: fix issues or commit.

    No HITL -- after MAX_REVIEW_ITERATIONS, commit regardless.
    """
    review_iter = state.get("review_iteration_count", 0)

    if state.get("issues_found") and review_iter < MAX_REVIEW_ITERATIONS:
        logger.debug("standard_dev.route_reviewer", decision="developer", review_iter=review_iter)
        return "developer"

    # Approved or max iterations reached -- commit
    if review_iter >= MAX_REVIEW_ITERATIONS and state.get("issues_found"):
        logger.info("standard_dev.route_reviewer", decision="git_commit",
                     reason="max_iterations", review_iter=review_iter)
    else:
        logger.debug("standard_dev.route_reviewer", decision="git_commit", approved=True)
    return "git_commit"


# ---------------------- Graph definition -------------------


def create_graph() -> StateGraph:
    """Create the standard dev graph: PM -> Developer -> Reviewer -> git_commit."""
    logger.info("standard_dev.graph.create")
    builder = StateGraph(StandardDevState)

    builder.add_node("pm", pm_node)
    builder.add_node("developer", developer_node)
    builder.add_node("reviewer", reviewer_node)
    builder.add_node("git_commit", git_commit_node)

    # Edges
    builder.add_edge(START, "pm")
    builder.add_edge("pm", "developer")
    builder.add_edge("developer", "reviewer")

    builder.add_conditional_edges(
        "reviewer",
        route_after_reviewer,
        {
            "developer": "developer",
            "git_commit": "git_commit",
        },
    )

    builder.add_edge("git_commit", END)

    return builder


# Compile (no interrupt_before -- no HITL)
checkpointer = MemorySaver()
graph = create_graph().compile(checkpointer=checkpointer)
logger.info("standard_dev.graph.compiled")

__all__ = ["graph", "StandardDevState"]
