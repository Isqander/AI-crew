"""
Simple Dev Graph
================

Minimal development graph for quick, simple tasks.

Flow::

    START -> Developer -> git_commit -> END

No HITL, no QA loop, no planning phase.
Single Developer agent writes code and commits directly.
"""

import time as _time

import structlog
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from simple_dev.state import SimpleDevState
from common.logging import configure_logging
from common.git import make_git_commit_node

# Reuse the developer agent from dev_team
from dev_team.agents.developer import developer_agent as _dev_agent

configure_logging()
logger = structlog.get_logger()


# ---------------------- Node functions ----------------------


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


# git_commit_node created by shared factory from common.git
git_commit_node = make_git_commit_node("simple_dev")


# ---------------------- Graph definition ----------------------


def create_graph() -> StateGraph:
    """Create the simple dev graph: Developer -> git_commit -> END."""
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
