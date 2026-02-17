"""
Development Team Graph
======================

Main LangGraph definition for the AI development team.

Graph flow::

    START -> PM -> Analyst -> Architect -> Developer
                     |            |              |
                clarification  clarification   lint_check
                     |            |          +----+----+
                     +--- user ---+       clean?    issues?
                                            |          |
                                         security    Developer (fix lint)
                                             |
                                            QA
                                        +----+----+
                                      pass?    fail?
                                        |         |
                                    Reviewer   Developer
                                  +----+----+
                                issues?  approved?
                                  |       |
                               Developer devops (infra gen)
                          (after N)       |
                        architect_esc  git_commit
                                |         |
                          (still stuck) ci_check (if enabled)
                          human_esc   +----+----+
                             |      pass?    fail?
                          Developer   |       |
                                   pm_final Developer

Nodes:
  pm, analyst, architect, developer, security_review — agent nodes
  lint_check — runs linter in sandbox (Dev↔Lint loop until clean)
  qa — quality gate: sandbox/browser testing before Reviewer
  reviewer — code review after quality gate
  devops — generates infrastructure files (Dockerfile, CI/CD, Traefik)
  clarification — HITL interrupt for user input
  architect_escalation — architect reviews repeated Reviewer failures
  human_escalation — HITL interrupt when both Dev<->Reviewer and Architect fail
  git_commit — pushes code to GitHub and creates a PR
  ci_check — monitors GitHub Actions CI pipeline (Module 3.8)
  pm_final — PM's closing summary
"""

import os
import re
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
from dev_team.agents.devops import devops_agent


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

# Maximum Dev<->Lint iterations before forcing through
MAX_LINT_ITERATIONS = 3

# Security agent: enabled by env var or manifest parameter
USE_SECURITY_AGENT = os.getenv("USE_SECURITY_AGENT", "true").lower() in ("true", "1", "yes")

# QA sandbox agent: enabled by env var (can be disabled when sandbox is unavailable)
USE_QA_SANDBOX = os.getenv("USE_QA_SANDBOX", "true").lower() in ("true", "1", "yes")

# CI/CD integration: enabled by default (Module 3.8)
USE_CI_INTEGRATION = os.getenv("USE_CI_INTEGRATION", "true").lower() in ("true", "1", "yes")

# Lint check: enabled by env var (requires sandbox)
USE_LINT_CHECK = os.getenv("USE_LINT_CHECK", "true").lower() in ("true", "1", "yes")

# DevOps agent: generates infrastructure files (Dockerfile, CI/CD, Traefik)
USE_DEVOPS_AGENT = os.getenv("USE_DEVOPS_AGENT", "true").lower() in ("true", "1", "yes")


def route_after_developer(
    state: DevTeamState,
) -> Literal["lint_check", "security_review", "qa"]:
    """Router: After developer, run quality gate before Reviewer.

    Flow: Developer → lint_check → security_review(optional) → qa → reviewer.
    Lint runs on every developer iteration to keep the gate strict.
    """
    if USE_LINT_CHECK:
        logger.info("router.after_developer", decision="lint_check")
        return "lint_check"

    if USE_SECURITY_AGENT:
        logger.info("router.after_developer", decision="security_review")
        return "security_review"
    logger.info("router.after_developer", decision="qa")
    return "qa"


def _detect_language(state: DevTeamState) -> str:
    """Detect primary language from tech_stack or code_files."""
    tech_stack = state.get("tech_stack", [])
    for t in tech_stack:
        low = t.lower()
        if "python" in low or "fastapi" in low or "flask" in low or "django" in low:
            return "python"
        if "node" in low or "express" in low or "next" in low or "react" in low:
            return "javascript"
        if "typescript" in low or "ts" in low:
            return "typescript"
        if "go" in low or "golang" in low:
            return "go"
        if "rust" in low:
            return "rust"

    # Fallback: check file extensions
    for f in state.get("code_files", []):
        path = (f.get("path") or "").lower()
        if path.endswith(".py"):
            return "python"
        if path.endswith((".js", ".jsx")):
            return "javascript"
        if path.endswith((".ts", ".tsx")):
            return "typescript"
        if path.endswith(".go"):
            return "go"
        if path.endswith(".rs"):
            return "rust"

    return "python"


def lint_check_node(state: DevTeamState, config=None) -> dict:
    """Lint check node — runs linter in sandbox on generated code.

    Uses ``run_lint`` tool under the hood (ruff for Python, eslint for JS/TS,
    go vet for Go). Writes lint_status / lint_log into state.
    """
    from dev_team.tools.sandbox import SandboxClient, _auto_lint_command, _lint_install_commands

    code_files = state.get("code_files", [])
    if not code_files:
        logger.info("lint_check.skip", reason="no code files")
        return {
            "lint_status": "skipped",
            "lint_log": "Lint skipped: no code files.",
            "current_agent": "lint_check",
        }

    language = _detect_language(state)
    lint_command = _auto_lint_command(language)
    install_cmds = _lint_install_commands(language)
    commands = install_cmds + [f"{lint_command} 2>&1"]

    sandbox_files = [
        {"path": f["path"], "content": f["content"]}
        for f in code_files
        if f.get("path") and f.get("content")
    ]

    logger.info("lint_check.start", language=language, files=len(sandbox_files),
                lint_command=lint_command)

    try:
        client = SandboxClient()
        result = client.execute(
            language=language,
            code_files=sandbox_files,
            commands=commands,
            timeout=60,
            memory_limit="128m",
        )

        exit_code = result.get("exit_code", -1)
        stdout = result.get("stdout", "").strip()
        stderr = result.get("stderr", "").strip()
        lint_output = stdout
        if stderr:
            lint_output += f"\n{stderr}" if lint_output else stderr

        lint_text = (lint_output or "").strip()
        lint_warnings: list[str] = []
        lint_errors: list[str] = []

        non_blocking_codes_raw = os.getenv(
            "LINT_NON_BLOCKING_CODES",
            "E501,W291,W293,I001",
        )
        non_blocking_codes = {
            code.strip().upper()
            for code in non_blocking_codes_raw.split(",")
            if code.strip()
        }

        for raw_line in lint_text.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            # Ruff-style line: path:line:col: CODE message
            code_match = re.search(r":\d+:\d+:\s+([A-Z]\d{3,4})\b", line)
            if code_match:
                code = code_match.group(1).upper()
                if code in non_blocking_codes:
                    lint_warnings.append(line)
                else:
                    lint_errors.append(line)
                continue

            lower = line.lower()
            if " warning " in f" {lower} " or lower.startswith("warning"):
                lint_warnings.append(line)
                continue
            if " error " in f" {lower} " or lower.startswith("error"):
                lint_errors.append(line)

        # Determine lint status
        if result.get("error"):
            # Sandbox infrastructure error (connection refused, timeout, etc.)
            lint_status = "error"
            lint_log = f"Lint check error: {result['error']}"
        elif lint_errors:
            lint_status = "issues"
            lint_log = f"Lint: ISSUES FOUND (exit_code={exit_code})\n\n{lint_output[:3000]}"
        elif lint_warnings:
            lint_status = "warnings"
            lint_log = f"Lint: WARNINGS (non-blocking, exit_code={exit_code})\n\n{lint_output[:3000]}"
        elif exit_code == 0:
            lint_status = "clean"
            lint_log = "Lint: CLEAN — no issues found."
        else:
            lint_status = "issues"
            lint_log = f"Lint: ISSUES FOUND (exit_code={exit_code})\n\n{lint_output[:3000]}"

        lint_iter = state.get("lint_iteration_count", 0) + 1
        logger.info("lint_check.done", status=lint_status, exit_code=exit_code,
                     lint_iteration=lint_iter)

        return {
            "lint_status": lint_status,
            "lint_log": lint_log,
            "lint_warnings": lint_warnings[:50],
            "lint_errors": lint_errors[:50],
            "lint_iteration_count": lint_iter,
            "current_agent": "lint_check",
        }

    except Exception as exc:
        logger.error("lint_check.error", error=str(exc)[:300])
        return {
            "lint_status": "error",
            "lint_log": f"Lint check error: {str(exc)[:300]}",
            "lint_iteration_count": state.get("lint_iteration_count", 0) + 1,
            "current_agent": "lint_check",
        }


def route_after_lint(
    state: DevTeamState,
) -> Literal["developer", "security_review", "qa"]:
    """Router: After lint check, decide next step.

    Lint CLEAN/WARNINGS → security_review (if enabled) or qa.
    Lint ISSUES → developer (to fix lint errors).
    After MAX_LINT_ITERATIONS → force through to qa (don't loop forever).
    Lint skipped/error → proceed to qa.
    """
    lint_status = state.get("lint_status", "")
    lint_iter = state.get("lint_iteration_count", 0)

    # Clean/warnings — proceed to security/qa
    if lint_status in ("clean", "warnings", "skipped", "error"):
        if USE_SECURITY_AGENT:
            logger.info("router.after_lint", decision="security_review",
                        lint_status=lint_status)
            return "security_review"
        logger.info("router.after_lint", decision="qa", lint_status=lint_status)
        return "qa"

    # Issues found — send back to developer, unless max iterations reached
    if lint_iter >= MAX_LINT_ITERATIONS:
        logger.warning("router.after_lint", decision="qa",
                        lint_status=lint_status, lint_iter=lint_iter,
                        reason="max_lint_iterations_reached")
        if USE_SECURITY_AGENT:
            return "security_review"
        return "qa"

    logger.info("router.after_lint", decision="developer",
                lint_status=lint_status, lint_iter=lint_iter)
    return "developer"


def _approved_next_step() -> str:
    """Return the next node after approval: devops (if enabled) or git_commit."""
    return "devops" if USE_DEVOPS_AGENT else "git_commit"


def route_after_reviewer(
    state: DevTeamState,
) -> Literal["developer", "architect_escalation", "human_escalation", "devops", "git_commit", "pm_final"]:
    """
    Router: After Reviewer, determine next step.

    Escalation ladder:
      1) <= N Dev<->Reviewer iterations -> send back to developer
      2) After N iterations (architect not yet involved) -> architect_escalation
      3) After architect intervened and another N iterations -> human_escalation
      4) If no issues / approved -> devops (if enabled) -> git_commit or pm_final
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

    # If approved, proceed to devops -> git_commit (QA quality gate already passed)
    test_results = state.get("test_results", {})
    if test_results.get("approved", False):
        next_step = _approved_next_step()
        logger.debug("router.after_reviewer", decision=next_step, approved=True)
        return next_step

    # Otherwise, final PM review
    logger.debug("router.after_reviewer", decision="pm_final")
    return "pm_final"


def route_after_qa(
    state: DevTeamState,
) -> Literal["reviewer", "developer"]:
    """Router: After QA quality gate, review or fix.

    QA runs code in a sandbox. If tests pass -> reviewer.
    If tests fail -> developer (to fix runtime issues).
    """
    test_results = state.get("test_results", {})
    sandbox_results = state.get("sandbox_results") or {}

    # QA approved (LLM verdict or tests passed)
    if test_results.get("approved", False):
        logger.debug("router.after_qa", decision="reviewer", approved=True)
        return "reviewer"

    # QA skipped (no code files)
    if test_results.get("skipped", False):
        logger.debug("router.after_qa", decision="reviewer", skipped=True)
        return "reviewer"

    # Sandbox exit_code == 0 as fallback
    if sandbox_results.get("exit_code") == 0:
        logger.debug("router.after_qa", decision="reviewer", exit_code=0)
        return "reviewer"

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
) -> Literal["developer", "devops", "git_commit"]:
    """
    After architect escalation: if approved -> devops/git_commit, else -> developer.
    """
    test_results = state.get("test_results", {})
    if test_results.get("approved", False):
        return _approved_next_step()
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
    5. Lint quality gate
    6. Security review (optional)
    7. QA quality gate (sandbox/browser; may send back to developer)
    8. Reviewer checks code quality (may send back to developer)
    9. DevOps generates infrastructure (Dockerfile, CI/CD, Traefik)
    10. Git commit (if approved)
    11. CI check (if enabled)
    12. PM final review
    """

    # Create the graph
    logger.info("graph.create")
    builder = StateGraph(DevTeamState)

    # Add nodes
    builder.add_node("pm", pm_agent)
    builder.add_node("analyst", analyst_agent)
    builder.add_node("architect", architect_agent)
    builder.add_node("developer", developer_agent)
    if USE_LINT_CHECK:
        builder.add_node("lint_check", lint_check_node)
    builder.add_node("security_review", security_agent)
    builder.add_node("reviewer", reviewer_agent)
    builder.add_node("qa", qa_agent)
    builder.add_node("clarification", clarification_node)
    builder.add_node("architect_escalation", architect_escalation_node)
    builder.add_node("human_escalation", human_escalation_node)
    if USE_DEVOPS_AGENT:
        builder.add_node("devops", devops_agent)
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

    # Developer -> (lint_check | security_review | qa)
    # Lint check runs on every pass as part of the quality gate
    if USE_LINT_CHECK:
        builder.add_conditional_edges(
            "developer",
            route_after_developer,
            {
                "lint_check": "lint_check",
                "security_review": "security_review",
                "qa": "qa",
            }
        )
        # Lint check -> (developer | security_review | qa)
        builder.add_conditional_edges(
            "lint_check",
            route_after_lint,
            {
                "developer": "developer",
                "security_review": "security_review",
                "qa": "qa",
            }
        )
    else:
        builder.add_conditional_edges(
            "developer",
            route_after_developer,
            {
                "lint_check": "security_review" if USE_SECURITY_AGENT else "qa",
                "security_review": "security_review",
                "qa": "qa",
            }
        )

    # Security review -> QA quality gate
    builder.add_edge("security_review", "qa")

    # Reviewer -> (developer | architect_escalation | human_escalation | devops | git_commit | pm_final)
    reviewer_edges = {
        "developer": "developer",
        "architect_escalation": "architect_escalation",
        "human_escalation": "human_escalation",
        "git_commit": "git_commit",
        "pm_final": "pm_final",
    }
    if USE_DEVOPS_AGENT:
        reviewer_edges["devops"] = "devops"
    builder.add_conditional_edges(
        "reviewer",
        route_after_reviewer,
        reviewer_edges,
    )

    # QA (quality gate) -> (reviewer | developer)
    builder.add_conditional_edges(
        "qa",
        route_after_qa,
        {
            "reviewer": "reviewer",
            "developer": "developer",
        }
    )

    # Architect escalation -> (developer or devops/git_commit)
    arch_esc_edges = {
        "developer": "developer",
        "git_commit": "git_commit",
    }
    if USE_DEVOPS_AGENT:
        arch_esc_edges["devops"] = "devops"
    builder.add_conditional_edges(
        "architect_escalation",
        route_after_architect_escalation,
        arch_esc_edges,
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

    # DevOps -> git_commit (if DevOps enabled)
    if USE_DEVOPS_AGENT:
        builder.add_edge("devops", "git_commit")

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
