"""
Standard Dev State
==================

State for the standard_dev graph.
PM -> Developer -> Reviewer -> git_commit.
"""

from typing import TypedDict, Annotated

try:
    from typing import NotRequired
except ImportError:
    from typing_extensions import NotRequired

from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage

# Import shared types from common module (single source of truth)
from common.types import CodeFile


class StandardDevState(TypedDict):
    """State for the standard development graph."""

    # === Input ===
    task: str
    repository: NotRequired[str]
    context: NotRequired[str]

    # === PM Output ===
    requirements: list[str]

    # === Developer Output ===
    code_files: list[CodeFile]
    implementation_notes: str

    # === Reviewer Output ===
    review_comments: list[str]
    test_results: dict
    issues_found: list[str]

    # === Final Output ===
    pr_url: NotRequired[str]
    commit_sha: NotRequired[str]
    working_branch: NotRequired[str]
    working_repo: NotRequired[str]
    summary: str

    # === Conversation ===
    messages: Annotated[list[BaseMessage], add_messages]

    # === Control ===
    current_agent: str
    next_agent: NotRequired[str]
    review_iteration_count: int
    needs_clarification: bool  # Always False in this graph (no HITL)
    error: NotRequired[str]
