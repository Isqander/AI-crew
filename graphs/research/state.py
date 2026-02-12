"""
Research State
==============

State for the research graph.
Researcher searches the web and synthesizes a report.
"""

from typing import TypedDict, Annotated

try:
    from typing import NotRequired
except ImportError:
    from typing_extensions import NotRequired

from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class ResearchSource(TypedDict):
    """A source found during research."""
    title: str
    url: str
    snippet: str


class ResearchState(TypedDict):
    """State for the research graph."""

    # === Input ===
    task: str
    context: NotRequired[str]

    # === Research Output ===
    search_results: NotRequired[str]       # Raw search results
    fetched_content: NotRequired[str]      # Content from fetched URLs
    sources: list[ResearchSource]          # Structured source list
    findings: NotRequired[str]             # Raw findings before synthesis
    report: str                            # Final synthesized report

    # === Final Output ===
    summary: str

    # === Conversation ===
    messages: Annotated[list[BaseMessage], add_messages]

    # === Control ===
    current_agent: str
    error: NotRequired[str]
