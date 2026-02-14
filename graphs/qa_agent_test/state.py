"""
QA Agent Test State
===================

State for the qa_agent_test graph.
Flow: Developer -> QA -> Report.
"""

from typing import TypedDict, Annotated

try:
    from typing import NotRequired
except ImportError:
    from typing_extensions import NotRequired

from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class CodeFile(TypedDict):
    """Represents a generated code file."""
    path: str
    content: str
    language: str


class QAAgentTestState(TypedDict):
    """State for QA agent testing workflow."""

    # Input
    task: str
    context: NotRequired[str]

    # Developer
    code_files: list[CodeFile]
    implementation_notes: str
    tech_stack: list[str]

    # QA
    test_results: dict
    sandbox_results: NotRequired[dict]
    browser_test_results: NotRequired[dict]
    issues_found: list[str]
    review_iteration_count: int

    # Output
    qa_report: str
    summary: str

    # Conversation
    messages: Annotated[list[BaseMessage], add_messages]

    # Control
    current_agent: str
    next_agent: NotRequired[str]
    error: NotRequired[str]

