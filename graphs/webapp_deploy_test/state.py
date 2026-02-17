"""
WebApp Deploy Test State
========================

State for the fast web-app smoke-to-deploy graph.
Flow: Developer -> QA (max 1 retry) -> DevOps -> git_commit -> deploy -> report.
"""

from typing import TypedDict, Annotated

try:
    from typing import NotRequired
except ImportError:
    from typing_extensions import NotRequired

from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage
from common.types import CodeFile


class WebAppDeployTestState(TypedDict):
    """Shared state for webapp_deploy_test graph."""

    # Input
    task: str
    context: NotRequired[str]
    repository: NotRequired[str]

    # Build output
    code_files: list[CodeFile]
    implementation_notes: str
    tech_stack: list[str]
    requirements: NotRequired[list[str]]
    architecture: NotRequired[dict]

    # QA / review
    test_results: dict
    sandbox_results: NotRequired[dict]
    browser_test_results: NotRequired[dict]
    issues_found: list[str]
    review_comments: list[str]
    review_iteration_count: int
    qa_retry_count: NotRequired[int]

    # Deploy / git
    infra_files: NotRequired[list[dict]]
    deploy_url: NotRequired[str]
    deploy_status: NotRequired[str]
    deploy_repo: NotRequired[str]
    deploy_branch: NotRequired[str]
    ci_status: NotRequired[str]
    ci_log: NotRequired[str]
    ci_run_id: NotRequired[int]
    ci_run_url: NotRequired[str]
    pr_url: NotRequired[str]
    commit_sha: NotRequired[str]
    working_branch: NotRequired[str]
    working_repo: NotRequired[str]

    # Output
    summary: str
    deploy_report: NotRequired[str]

    # Conversation / control
    messages: Annotated[list[BaseMessage], add_messages]
    current_agent: str
    next_agent: NotRequired[str]
    error: NotRequired[str]
