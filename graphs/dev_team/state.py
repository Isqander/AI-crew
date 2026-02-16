"""
DevTeam State Definition
========================

Defines ``DevTeamState`` — the shared TypedDict passed between all
LangGraph nodes in the dev-team workflow.

Key sections:
  - **Input** — task, repository, context (provided by the user)
  - **Agent outputs** — requirements, architecture, code_files, etc.
  - **Conversation** — LangGraph message history (auto-accumulated)
  - **Control flow** — current_agent, needs_clarification, qa counters
"""

from typing import TypedDict, Annotated
try:
    from typing import NotRequired  # Python 3.11+
except ImportError:
    from typing_extensions import NotRequired  # Python 3.9-3.10

from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage

# Import shared types from common module (single source of truth)
from common.types import CodeFile, UserStory, ArchitectureDecision


class DevTeamState(TypedDict):
    """
    Main state for the development team graph.
    
    This state is passed between all agents and accumulates
    the work products of each stage.
    """
    
    # === Input ===
    task: str                                    # Original task description
    repository: NotRequired[str]                 # Target GitHub repository URL
    context: NotRequired[str]                    # Additional context/requirements
    
    # === Task Classification (Wave 1) ===
    task_type: NotRequired[str]                  # "new_project", "bugfix", "feature", "refactor"
    task_complexity: NotRequired[int]            # 1-10 (from Switch-Agent / router)
    
    # === Analyst Output ===
    requirements: list[str]                      # Extracted requirements
    user_stories: list[UserStory]                # User stories
    
    # === Architect Output ===
    architecture: dict                           # Architecture specification
    tech_stack: list[str]                        # Chosen technologies
    architecture_decisions: list[ArchitectureDecision]
    
    # === Developer Output ===
    code_files: list[CodeFile]                   # Generated code files
    implementation_notes: str                    # Notes about implementation
    
    # === Reviewer Output ===
    review_comments: list[str]                   # Code review feedback
    test_results: dict                           # Test / sandbox execution results
    issues_found: list[str]                      # Issues to fix
    
    # === Final Output ===
    pr_url: NotRequired[str]                     # Created PR URL
    commit_sha: NotRequired[str]                 # Commit SHA
    summary: str                                 # Final summary
    
    # === Conversation ===
    messages: Annotated[list[BaseMessage], add_messages]
    
    # === Control Flow ===
    current_agent: str                           # Currently active agent
    next_agent: NotRequired[str]                 # Next agent to invoke
    
    # === Human-in-the-Loop ===
    needs_clarification: bool                    # Flag for HITL
    clarification_question: NotRequired[str]     # Question for user
    clarification_context: NotRequired[str]      # Context for the question
    clarification_response: NotRequired[str]     # User's response
    
    # === Iteration control ===
    review_iteration_count: int                  # Dev↔Reviewer/QA loop counter (reset after architect escalation)
    architect_escalated: bool                    # True after first architect escalation in Dev↔Reviewer loop

    # === Error Handling ===
    error: NotRequired[str]                      # Error message if any
    retry_count: int                             # Number of retries

    # === Wave 2: Git-based Workflow ===
    working_branch: NotRequired[str]             # "ai/task-20260208-123456"
    working_repo: NotRequired[str]               # "owner/repo"
    file_manifest: NotRequired[list[str]]        # Files tracked in the branch

    # === Wave 2: Sandbox ===
    sandbox_results: NotRequired[dict]           # {stdout, stderr, exit_code, tests_passed}

    # === Visual QA (Browser E2E testing) ===
    browser_test_results: NotRequired[dict]      # See ARCHITECTURE_V2 Appendix C.5

    # === Wave 2: Security ===
    security_review: NotRequired[dict]           # {critical: [], warnings: [], info: []}

    # === Wave 2: Deploy ===
    deploy_url: NotRequired[str]                 # "https://app.31.59.58.143.nip.io"
    infra_files: NotRequired[list[dict]]         # [{path, content}]

    # === Wave 2: Lint Check ===
    lint_status: NotRequired[str]                # "clean", "issues", "error", "skipped"
    lint_log: NotRequired[str]                   # Lint output (ruff/eslint/go vet)
    lint_iteration_count: NotRequired[int]       # Dev↔Lint loop counter

    # === Wave 2: CI/CD (Module 3.8) ===
    ci_status: NotRequired[str]                  # "pending", "running", "success", "failure", "timeout"
    ci_log: NotRequired[str]                     # CI output / failure summary
    ci_run_id: NotRequired[int]                  # GitHub Actions workflow run ID
    ci_run_url: NotRequired[str]                 # URL to the CI run

    # === Wave 2: CLI ===
    cli_agent_output: NotRequired[str]
    cli_agent_role: NotRequired[str]             # "developer", "architect", etc.
    execution_mode: NotRequired[str]             # "auto" | "internal" | "cli"
    cli_tool: NotRequired[str]                   # "claude" | "codex"


def create_initial_state(
    task: str,
    repository: str | None = None,
    context: str | None = None
) -> DevTeamState:
    """
    Create an initial state for a new task.
    
    Args:
        task: The task description
        repository: Optional GitHub repository URL
        context: Optional additional context
        
    Returns:
        Initialized DevTeamState
    """
    # Build state dict, only including NotRequired fields if they have values
    state: dict = {
        # Required input
        "task": task,
        
        # Required outputs (empty by default)
        "requirements": [],
        "user_stories": [],
        "architecture": {},
        "tech_stack": [],
        "architecture_decisions": [],
        "code_files": [],
        "implementation_notes": "",
        "review_comments": [],
        "test_results": {},
        "issues_found": [],
        "summary": "",
        
        # Conversation
        "messages": [],
        
        # Control
        "current_agent": "pm",
        
        # HITL
        "needs_clarification": False,
        
        # Iteration control
        "review_iteration_count": 0,
        "architect_escalated": False,

        # Error handling
        "retry_count": 0,
    }
    
    # Only add NotRequired fields if they have values
    if repository is not None:
        state["repository"] = repository
    if context is not None:
        state["context"] = context
    
    return DevTeamState(**state)
