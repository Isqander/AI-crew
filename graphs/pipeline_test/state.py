"""
Pipeline Test State
===================

State for the pipeline_test graph.
Flow: Developer → Lint (loop) → QA (sandbox + visual) → Report.

Tests: lint checking, Dev↔Lint fix loop, sandbox tests, visual QA.
"""

from typing import TypedDict, Annotated

try:
    from typing import NotRequired
except ImportError:
    from typing_extensions import NotRequired

from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage
from common.types import CodeFile


class PipelineTestState(TypedDict):
    """State for full pipeline testing workflow."""

    # Input
    task: str
    context: NotRequired[str]

    # Developer
    code_files: list[CodeFile]
    implementation_notes: str
    tech_stack: list[str]
    architecture: NotRequired[dict]

    # Lint
    lint_status: NotRequired[str]       # "clean", "issues", "error", "skipped"
    lint_log: NotRequired[str]
    lint_iteration_count: NotRequired[int]

    # QA
    test_results: dict
    sandbox_results: NotRequired[dict]
    browser_test_results: NotRequired[dict]
    issues_found: list[str]
    review_comments: list[str]
    review_iteration_count: int

    # Output
    pipeline_report: str
    summary: str

    # Conversation
    messages: Annotated[list[BaseMessage], add_messages]

    # Control
    current_agent: str
    next_agent: NotRequired[str]
    error: NotRequired[str]
