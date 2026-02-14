"""
Development Team Graph
======================

Main LangGraph definition for the AI development team.

Graph flow::

    START -> PM -> Analyst -> Architect -> Developer
                     |            |              |
                clarification  clarification   +------------------+
                     |            |          security?        (fix loop)
                     +--- user ---+             |                |
                                          security_review    Reviewer
                                                |          +----+----+
                                             Reviewer  issues_found? approved?
                                                          |         |
                                                      Developer    QA (sandbox)
                                                          |      +----+----+
                                                    (after N)  pass?    fail?
                                                  architect_esc  |       |
                                                          |   git_commit Developer
                                                    (still stuck)
                                                  human_escalation -> Developer

Nodes:
  pm, analyst, architect, developer, security_review — agent nodes
  reviewer — code review (was formerly "qa")
  qa — sandbox-based testing (runs code, checks results)
  clarification — HITL interrupt for user input
  architect_escalation — architect reviews repeated Reviewer failures
  human_escalation — HITL interrupt when both Dev<->Reviewer and Architect fail
  git_commit — pushes code to GitHub and creates a PR
  pm_final — PM's closing summary
"""

import os
from typing import Literal

import structlog
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

# NOTE: Aegra loads this file via importlib with module name "graphs.{graph_id}",
# which sets __package__ = "graphs" instead of "graphs.dev_team".
# Relative imports (from .state, from .agents) would resolve against "graphs.*"
# and fail. Use absolute imports based on sys.path (/app/graphs -> "dev_team.*").
from dev_team.state import DevTeamState
from dev_team.logging_config import configure_logging

from dev_team.agents.pm import pm_agent
from dev_team.agents.analyst import analyst_agent
from dev_team.agents.architect import architect_agent
from dev_team.agents.developer import developer_agent
from dev_team.agents.reviewer import reviewer_agent
from dev_team.agents.qa import qa_agent
from dev_team.agents.security import security_agent
from dev_team.tools.git_workspace import commit_and_create_pr


configure_logging()
logger = structlog.get_logger()


def should_clarify(state: DevTeamState) -> Literal["clarification", "continue"]:
    """
    Router: Check if clarification is needed from user.
    """
    needs = state.get("needs_clarification", False)
    decision = "clarification" if needs else "continue"
    logger.info("router.should_clarify", needs_clarification=needs, decision=decision,
                current_agent=state.get("current_agent"))
    if needs:
        return "clarification"
    return "continue"


def route_after_analyst(state: DevTeamState) -> Literal["clarification", "architect"]:
    """
    Router: After analyst, check if clarification needed.
    """
    needs = state.get("needs_clarification", False)
    decision = "clarification" if needs else "architect"
    logger.info("router.after_analyst", needs_clarification=needs, decision=decision,
                requirements_count=len(state.get("requirements", [])))
    if needs:
        return "clarification"
    return "architect"


def route_after_architect(state: DevTeamState) -> Literal["clarification", "developer"]:
    """
    Router: After architect, check if approval needed.
    """
    needs = state.get("needs_clarification", False)
    decision = "clarification" if needs else "developer"
    logger.info("router.after_architect", needs_clarification=needs, decision=decision,
                has_architecture=bool(state.get("architecture")),
                tech_stack=state.get("tech_stack", []))
    if needs:
        return "clarification"
    return "developer"


# Maximum Dev<->Reviewer iterations before escalation
MAX_REVIEW_ITERATIONS_BEFORE_ARCHITECT = 3
MAX_REVIEW_ITERATIONS_BEFORE_HUMAN = 3  # After architect already escalated once

# Security agent: enabled by env var or manifest parameter
USE_SECURITY_AGENT = os.getenv("USE_SECURITY_AGENT", "true").lower() in ("true", "1", "yes")

# QA sandbox agent: enabled by env var (can be disabled when sandbox is unavailable)
USE_QA_SANDBOX = os.getenv("USE_QA_SANDBOX", "true").lower() in ("true", "1", "yes")


def route_after_developer(
    state: DevTeamState,
) -> Literal["security_review", "reviewer"]:
    """Router: After developer, optionally run security review before Reviewer.

    Security review is enabled when ``USE_SECURITY_AGENT`` is True.
    When the Dev<->Reviewer loop is iterating (review_iteration_count > 0),
    security review is skipped to avoid redundant re-scans.
    """
    review_iter = state.get("review_iteration_count", 0)
    if USE_SECURITY_AGENT and review_iter == 0:
        logger.info("router.after_developer", decision="security_review")
        return "security_review"
    logger.info("router.after_developer", decision="reviewer", review_iter=review_iter)
    return "reviewer"


def route_after_reviewer(
    state: DevTeamState,
) -> Literal["developer", "architect_escalation", "human_escalation", "qa", "pm_final"]:
    """
    Router: After Reviewer, determine next step.

    Escalation ladder:
      1) <= N Dev<->Reviewer iterations -> send back to developer
      2) After N iterations (architect not yet involved) -> architect_escalation
      3) After architect intervened and another N iterations -> human_escalation
      4) If no issues / approved -> qa (sandbox testing) or pm_final
    """
    # If there are issues, apply escalation logic
    if state.get("issues_found"):
        review_iter = state.get("review_iteration_count", 0)
        architect_escalated = state.get("architect_escalated", False)

        if not architect_escalated and review_iter >= MAX_REVIEW_ITERATIONS_BEFORE_ARCHITECT:
            logger.info("router.after_reviewer", decision="architect_escalation", review_iter=review_iter)
            return "architect_escalation"

        if architect_escalated and review_iter >= MAX_REVIEW_ITERATIONS_BEFORE_HUMAN:
            logger.info("router.after_reviewer", decision="human_escalation", review_iter=review_iter)
            return "human_escalation"

        logger.debug("router.after_reviewer", decision="developer",
                     issues=len(state.get("issues_found", [])), review_iter=review_iter)
        return "developer"

    # If approved, proceed to QA sandbox testing
    test_results = state.get("test_results", {})
    if test_results.get("approved", False):
        logger.debug("router.after_reviewer", decision="qa", approved=True)
        return "qa"

    # Otherwise, final PM review
    logger.debug("router.after_reviewer", decision="pm_final")
    return "pm_final"


def route_after_qa(
    state: DevTeamState,
) -> Literal["git_commit", "developer"]:
    """Router: After QA sandbox testing, commit or fix.

    QA runs code in a sandbox. If tests pass -> git_commit.
    If tests fail -> developer (to fix runtime issues).
    """
    test_results = state.get("test_results", {})
    sandbox_results = state.get("sandbox_results") or {}

    # QA approved (LLM verdict or tests passed)
    if test_results.get("approved", False):
        logger.debug("router.after_qa", decision="git_commit", approved=True)
        return "git_commit"

    # QA skipped (no code files)
    if test_results.get("skipped", False):
        logger.debug("router.after_qa", decision="git_commit", skipped=True)
        return "git_commit"

    # Sandbox exit_code == 0 as fallback
    if sandbox_results.get("exit_code") == 0:
        logger.debug("router.after_qa", decision="git_commit", exit_code=0)
        return "git_commit"

    # Tests failed -> developer
    logger.debug("router.after_qa", decision="developer",
                 exit_code=sandbox_results.get("exit_code"))
    return "developer"


def clarification_node(state: DevTeamState) -> dict:
    """
    Human-in-the-loop node for clarification.

    This node is an interrupt point - execution pauses here
    until user provides clarification_response.
    """
    logger.info("node.clarification", status="waiting_for_user")
    return {
        "current_agent": "waiting_for_user",
    }


def process_clarification(state: DevTeamState) -> dict:
    """
    Process clarification response and route to appropriate agent.
    """
    # Clear the clarification flag
    current_agent = state.get("current_agent", "pm")
    logger.info("node.process_clarification", agent=current_agent)

    return {
        "needs_clarification": False,
    }


def architect_escalation_node(state: DevTeamState, config=None) -> dict:
    """
    Architect reviews repeated Dev<->Reviewer failures and decides
    which issues are truly critical vs cosmetic/waivable.
    """
    from dev_team.agents.architect import get_architect_agent
    agent = get_architect_agent()
    return agent.review_qa_escalation(state, config=config)


def route_after_architect_escalation(
    state: DevTeamState,
) -> Literal["developer", "git_commit"]:
    """
    After architect escalation: if approved -> git_commit, else -> developer.
    """
    test_results = state.get("test_results", {})
    if test_results.get("approved", False):
        return "git_commit"
    return "developer"


def human_escalation_node(state: DevTeamState) -> dict:
    """
    After both Dev<->Reviewer and Architect escalation failed to converge,
    ask the human for guidance via the HITL interrupt mechanism.

    The node sets needs_clarification=True and pauses the graph.
    """
    issues = state.get("issues_found", [])
    review_iter = state.get("review_iteration_count", 0)
    issues_text = "\n".join(f"  - {i}" for i in issues) if issues else "  (see review comments)"

    logger.info("node.human_escalation", review_iter=review_iter, issues=len(issues))

    question = (
        f"Dev and Reviewer could not resolve the following issues after "
        f"multiple iterations (including Architect review):\n\n"
        f"{issues_text}\n\n"
        f"Please advise:\n"
        f"1. Which issues can be waived / accepted as-is?\n"
        f"2. How should the remaining issues be fixed?\n"
        f"3. Or should we proceed with the current code?"
    )

    return {
        "needs_clarification": True,
        "clarification_question": question,
        "clarification_context": "reviewer_human_escalation",
        "current_agent": "reviewer",
    }


def git_commit_node(state: DevTeamState) -> dict:
    """
    Commit generated code to GitHub via atomic Git tree API:
      1. Create a feature branch (``ai/<slug>-<timestamp>``)
      2. Batch-commit all code files in a single commit
      3. Open a pull request

    Uses ``commit_and_create_pr`` from ``git_workspace`` which provides:
    - Atomic commits (Git tree API -- one commit for all files)
    - Proper branch naming (``ai/<slug>-<timestamp>``)
    - Structured logging

    When no repository or GITHUB_TOKEN is configured the node
    gracefully skips the commit and returns the generated code
    in the summary so it is still visible in the chat.
    """
    import time as _time
    t0 = _time.monotonic()
    code_files = state.get("code_files", [])
    repository = state.get("repository") or os.getenv("GITHUB_DEFAULT_REPO", "")
    task = state.get("task", "AI-generated task")
    github_token_set = bool(os.getenv("GITHUB_TOKEN"))
    logger.info("node.git_commit.enter", repository=repository or "none",
                files=len(code_files), github_token_set=github_token_set,
                task_preview=task[:80])

    # ------------------------------------------------------------------
    # Guard: no repository -> return code in summary
    # ------------------------------------------------------------------
    if not repository:
        elapsed_ms = (_time.monotonic() - t0) * 1000
        logger.warning("node.git_commit.skip", reason="no_repository",
                       elapsed_ms=round(elapsed_ms))
        summary = _build_code_summary(code_files, task)
        return {
            "summary": summary,
            "current_agent": "complete",
        }

    # ------------------------------------------------------------------
    # Delegate to commit_and_create_pr (atomic commit + PR)
    # ------------------------------------------------------------------
    logger.info("node.git_commit.committing", repository=repository, files=len(code_files))
    result = commit_and_create_pr(
        repo_name=repository,
        task=task,
        code_files=code_files,
    )

    elapsed_ms = (_time.monotonic() - t0) * 1000

    # Handle errors gracefully
    if result.get("error") and result["files_committed"] == 0:
        logger.error("node.git_commit.failed", error=result["error"],
                     elapsed_ms=round(elapsed_ms))
        summary = _build_code_summary(code_files, task)
        return {
            "summary": f"Warning: Git commit failed: {result['error']}\n\n{summary}",
            "current_agent": "complete",
            "error": result["error"],
        }

    pr_url = result.get("pr_url", "")
    commit_sha = result.get("commit_sha", "")
    branch = result.get("working_branch", "")
    committed = result.get("files_committed", 0)

    logger.info("node.git_commit.success", pr_url=pr_url, branch=branch,
                commit_sha=commit_sha[:12] if commit_sha else "",
                files_committed=committed, elapsed_ms=round(elapsed_ms))

    return {
        "pr_url": pr_url,
        "commit_sha": commit_sha,
        "working_branch": branch,
        "working_repo": repository,
        "summary": (
            f"Created PR with {committed} file(s) on {repository}\n"
            f"Branch: {branch}\n"
            f"PR: {pr_url}"
        ),
        "current_agent": "complete",
    }


def _build_code_summary(code_files: list, task: str) -> str:
    """Format generated code files into a readable summary for the chat."""
    if not code_files:
        return f"Task completed: {task}\nNo code files were generated."

    parts = [f"Task completed: {task}", f"{len(code_files)} file(s) generated:\n"]
    for cf in code_files:
        path = cf.get("path", "unknown")
        lang = cf.get("language", "")
        content = cf.get("content", "")
        parts.append(f"### {path}")
        parts.append(f"```{lang}\n{content}\n```\n")
    return "\n".join(parts)


def create_graph() -> StateGraph:
    """
    Create the development team graph.

    Flow:
    1. PM receives and decomposes task
    2. Analyst gathers requirements (may ask for clarification)
    3. Architect designs solution (may ask for approval)
    4. Developer implements code
    5. Security review (optional, first pass only)
    6. Reviewer checks code quality (may send back to developer)
    7. QA runs code in sandbox (may send back to developer)
    8. Git commit (if approved)
    9. PM final review
    """

    # Create the graph
    logger.info("graph.create")
    builder = StateGraph(DevTeamState)

    # Add nodes
    builder.add_node("pm", pm_agent)
    builder.add_node("analyst", analyst_agent)
    builder.add_node("architect", architect_agent)
    builder.add_node("developer", developer_agent)
    builder.add_node("security_review", security_agent)
    builder.add_node("reviewer", reviewer_agent)
    builder.add_node("qa", qa_agent)
    builder.add_node("clarification", clarification_node)
    builder.add_node("architect_escalation", architect_escalation_node)
    builder.add_node("human_escalation", human_escalation_node)
    builder.add_node("git_commit", git_commit_node)
    builder.add_node("pm_final", pm_agent)  # Final PM review

    # Define edges

    # Start -> PM
    builder.add_edge(START, "pm")

    # PM -> Analyst
    builder.add_edge("pm", "analyst")

    # Analyst -> (clarification or architect)
    builder.add_conditional_edges(
        "analyst",
        route_after_analyst,
        {
            "clarification": "clarification",
            "architect": "architect",
        }
    )

    # Architect -> (clarification or developer)
    builder.add_conditional_edges(
        "architect",
        route_after_architect,
        {
            "clarification": "clarification",
            "developer": "developer",
        }
    )

    # Developer -> (security_review | reviewer)
    # Security review runs on first pass; skipped during Dev<->Reviewer fix loops
    builder.add_conditional_edges(
        "developer",
        route_after_developer,
        {
            "security_review": "security_review",
            "reviewer": "reviewer",
        }
    )

    # Security review -> Reviewer (always)
    builder.add_edge("security_review", "reviewer")

    # Reviewer -> (developer | architect_escalation | human_escalation | qa | pm_final)
    builder.add_conditional_edges(
        "reviewer",
        route_after_reviewer,
        {
            "developer": "developer",
            "architect_escalation": "architect_escalation",
            "human_escalation": "human_escalation",
            "qa": "qa",
            "pm_final": "pm_final",
        }
    )

    # QA (sandbox) -> (git_commit | developer)
    builder.add_conditional_edges(
        "qa",
        route_after_qa,
        {
            "git_commit": "git_commit",
            "developer": "developer",
        }
    )

    # Architect escalation -> (developer or git_commit)
    builder.add_conditional_edges(
        "architect_escalation",
        route_after_architect_escalation,
        {
            "developer": "developer",
            "git_commit": "git_commit",
        }
    )

    # Human escalation is an interrupt point -- after user responds,
    # route to developer to apply the human's guidance.
    builder.add_edge("human_escalation", "developer")

    # Clarification -> back to analyst
    # (clarification_context could be used for smarter routing later)
    builder.add_edge("clarification", "analyst")

    # Git commit -> END
    builder.add_edge("git_commit", END)

    # PM final -> END
    builder.add_edge("pm_final", END)

    return builder


# ===========================================
# Checkpointer (state persistence)
# ===========================================
# Aegra's DatabaseManager provides an AsyncPostgresSaver with a
# properly-managed connection pool.  It injects the checkpointer
# into the graph via  graph.copy(update={"checkpointer": ...})
# at execution time (see langgraph_service.py -> get_graph()).
#
# We compile with MemorySaver as a harmless default so that:
#   1) The module loads without requiring a live PostgreSQL connection
#   2) Standalone / test execution still works (in-memory state)
checkpointer = MemorySaver()

graph = create_graph().compile(
    checkpointer=checkpointer,
    interrupt_before=["clarification", "human_escalation"],  # Pause for human input
)
logger.info("graph.compiled", checkpointer="memory", note="Aegra injects PostgreSQL at runtime")


# Export for Aegra
__all__ = ["graph", "DevTeamState"]
