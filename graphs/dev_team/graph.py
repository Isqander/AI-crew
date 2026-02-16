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
from common.logging import configure_logging
from common.git import make_git_commit_node

from dev_team.agents.pm import pm_agent
from dev_team.agents.analyst import analyst_agent
from dev_team.agents.architect import architect_agent
from dev_team.agents.developer import developer_agent
from dev_team.agents.reviewer import reviewer_agent
from dev_team.agents.qa import qa_agent
from dev_team.agents.security import security_agent


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


def route_after_clarification(state: DevTeamState) -> Literal["analyst", "architect"]:
    """
    Router: After user provides clarification, route back to the requesting agent.

    Uses ``clarification_context`` to determine who originally asked for input.
    Defaults to analyst if context is ambiguous.
    """
    context = (state.get("clarification_context") or "").lower()
    if "architect" in context:
        logger.info("router.after_clarification", decision="architect", context=context)
        return "architect"
    logger.info("router.after_clarification", decision="analyst", context=context)
    return "analyst"


# Maximum Dev<->Reviewer iterations before escalation
MAX_REVIEW_ITERATIONS_BEFORE_ARCHITECT = 3
MAX_REVIEW_ITERATIONS_BEFORE_HUMAN = 3  # After architect already escalated once

# Security agent: enabled by env var or manifest parameter
USE_SECURITY_AGENT = os.getenv("USE_SECURITY_AGENT", "true").lower() in ("true", "1", "yes")

# QA sandbox agent: enabled by env var (can be disabled when sandbox is unavailable)
USE_QA_SANDBOX = os.getenv("USE_QA_SANDBOX", "true").lower() in ("true", "1", "yes")

# CI/CD integration: enabled by env var (Module 3.8)
USE_CI_INTEGRATION = os.getenv("USE_CI_INTEGRATION", "false").lower() in ("true", "1", "yes")


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


# git_commit_node created by shared factory from common.git
git_commit_node = make_git_commit_node("dev_team")


def ci_check_node(state: DevTeamState, config=None) -> dict:
    """CI/CD check node (Module 3.8).

    After git_commit pushes code, this node monitors the GitHub Actions
    CI workflow and reports the result.  When ``USE_CI_INTEGRATION``
    is ``False``, the node is not added to the graph.

    Workflow:
      1. Find the latest CI run for the working branch.
      2. Wait for it to complete (with timeout).
      3. If it failed, fetch job/step logs so Developer knows what to fix.
      4. Write ci_status / ci_log / ci_run_id / ci_run_url into state.
    """
    from dev_team.tools.github_actions import GitHubActionsClient

    repo = state.get("working_repo", "")
    branch = state.get("working_branch", "")

    if not repo or not branch:
        logger.warning("ci_check.skip", reason="no repo or branch in state")
        return {
            "ci_status": "skipped",
            "ci_log": "CI check skipped: no repository or branch configured.",
            "current_agent": "ci_check",
        }

    logger.info("ci_check.start", repo=repo, branch=branch)

    try:
        client = GitHubActionsClient()

        # 1. Find latest run
        latest = client.get_latest_workflow_run(repo, branch)
        run_id = latest.get("run_id")

        if run_id is None:
            logger.info("ci_check.no_run_found", repo=repo, branch=branch)
            return {
                "ci_status": "not_found",
                "ci_log": f"No CI workflow run found for branch '{branch}'.",
                "current_agent": "ci_check",
            }

        # 2. Wait for completion
        result = client.wait_for_completion(repo, run_id)
        conclusion = result.get("conclusion", "unknown")
        ci_log = f"CI {conclusion}: run #{run_id} ({result.get('elapsed_seconds', 0)}s)"

        # 3. If failed, get detailed logs
        if conclusion == "failure":
            try:
                logs = client.get_run_logs(repo, run_id)
                failed_steps = []
                for job in logs.get("jobs", []):
                    if job.get("conclusion") != "success":
                        for step in job.get("steps", []):
                            if step.get("conclusion") != "success":
                                failed_steps.append(
                                    f"  [{job['name']}] Step {step['number']}: "
                                    f"{step['name']} — {step.get('conclusion', 'unknown')}"
                                )
                if failed_steps:
                    ci_log += "\n\nFailed steps:\n" + "\n".join(failed_steps)
            except Exception as log_err:
                logger.warning("ci_check.logs_error", error=str(log_err)[:200])

        logger.info("ci_check.done", conclusion=conclusion, run_id=run_id)

        return {
            "ci_status": conclusion,
            "ci_log": ci_log,
            "ci_run_id": run_id,
            "ci_run_url": result.get("html_url", ""),
            "current_agent": "ci_check",
        }

    except Exception as exc:
        logger.error("ci_check.error", error=str(exc)[:300])
        return {
            "ci_status": "error",
            "ci_log": f"CI check error: {str(exc)[:300]}",
            "current_agent": "ci_check",
        }


def route_after_ci(
    state: DevTeamState,
) -> Literal["developer", "pm_final"]:
    """Router: After CI check, decide next step (Module 3.8).

    CI PASS (success) → pm_final (done)
    CI FAIL (failure/error/timeout) → developer (fix and retry)
    """
    ci_status = state.get("ci_status", "")

    if ci_status == "success":
        logger.info("router.after_ci", decision="pm_final", ci_status=ci_status)
        return "pm_final"

    if ci_status in ("skipped", "not_found"):
        # No CI configured or no run found — proceed to end
        logger.info("router.after_ci", decision="pm_final", ci_status=ci_status)
        return "pm_final"

    # failure, error, timeout, cancelled → developer must fix
    logger.info("router.after_ci", decision="developer", ci_status=ci_status)
    return "developer"


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

    # Clarification -> route back to requesting agent (analyst or architect)
    builder.add_conditional_edges(
        "clarification",
        route_after_clarification,
        {
            "analyst": "analyst",
            "architect": "architect",
        }
    )

    # Git commit -> CI check (if enabled) or END
    if USE_CI_INTEGRATION:
        builder.add_node("ci_check", ci_check_node)
        builder.add_edge("git_commit", "ci_check")
        builder.add_conditional_edges(
            "ci_check",
            route_after_ci,
            {
                "developer": "developer",
                "pm_final": "pm_final",
            }
        )
    else:
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
