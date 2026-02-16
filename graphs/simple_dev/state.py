"""
Simple Dev State
================

Minimal state for the simple_dev graph.
Only the fields needed for Developer -> git_commit.
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


class SimpleDevState(TypedDict):
    """Minimal state for the simple development graph."""

    # === Input ===
    task: str
    repository: NotRequired[str]
    context: NotRequired[str]

    # === Developer Output ===
    code_files: list[CodeFile]
    implementation_notes: str

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
    error: NotRequired[str]
