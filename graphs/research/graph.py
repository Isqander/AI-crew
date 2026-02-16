"""
Research Graph
==============

Universal research workflow for any topic.

Flow::

    START ─► Researcher ─► END

The Researcher node:
  1. Searches the web (DuckDuckGo)
  2. Fetches top URL contents
  3. Synthesizes a structured report with LLM

No HITL, no code generation — pure research and synthesis.
"""

import time as _time

import structlog
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from research.state import ResearchState
from research.agents.researcher import researcher_agent
from common.logging import configure_logging

configure_logging()
logger = structlog.get_logger()


def researcher_node(state: ResearchState, config=None) -> dict:
    """Researcher searches the web and produces a report."""
    t0 = _time.monotonic()
    logger.info("research.researcher.enter", task_len=len(state.get("task", "")),
                task_preview=state.get("task", "")[:80])
    result = researcher_agent(state, config=config)
    elapsed_ms = (_time.monotonic() - t0) * 1000
    summary_len = len(result.get("summary", ""))
    logger.info("research.researcher.exit", elapsed_ms=round(elapsed_ms),
                summary_chars=summary_len)
    return result


def create_graph() -> StateGraph:
    """Create the research graph: Researcher → END."""
    logger.info("research.graph.create")
    builder = StateGraph(ResearchState)

    builder.add_node("researcher", researcher_node)

    builder.add_edge(START, "researcher")
    builder.add_edge("researcher", END)

    return builder


# Compile (no interrupt_before — no HITL)
checkpointer = MemorySaver()
graph = create_graph().compile(checkpointer=checkpointer)
logger.info("research.graph.compiled")

__all__ = ["graph", "ResearchState"]
