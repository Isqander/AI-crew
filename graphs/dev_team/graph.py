"""
Development Team Graph
======================

Main LangGraph definition for the AI development team.

Graph flow::

    START ─► PM ─► Analyst ─► Architect ─► Developer ─► QA
                     │            │                       │
                clarification  clarification         ┌────┴────┐
                     │            │                  │         │
                     └─── user ───┘          issues_found?  approved?
                                                │         │
                                            Developer  git_commit ─► END
                                                │
                                          (after N iters)
                                        architect_escalation
                                                │
                                          (still stuck)
                                        human_escalation ─► Developer

Nodes:
  pm, analyst, architect, developer, qa — agent nodes
  clarification — HITL interrupt for user input
  architect_escalation — architect reviews repeated QA failures
  human_escalation — HITL interrupt when both Dev↔QA and Architect fail
  git_commit — pushes code to GitHub and creates a PR
  pm_final — PM's closing summary
"""

import os
from datetime import datetime, timezone
from typing import Literal

import structlog
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

# NOTE: Aegra loads this file via importlib with module name "graphs.{graph_id}",
# which sets __package__ = "graphs" instead of "graphs.dev_team".
# Relative imports (from .state, from .agents) would resolve against "graphs.*"
# and fail. Use absolute imports based on sys.path (/app/graphs → "dev_team.*").
from dev_team.state import DevTeamState
from dev_team.logging_config import configure_logging

from dev_team.agents.pm import pm_agent
from dev_team.agents.analyst import analyst_agent
from dev_team.agents.architect import architect_agent
from dev_team.agents.developer import developer_agent
from dev_team.agents.qa import qa_agent
from dev_team.tools.github import get_github_client


configure_logging()
logger = structlog.get_logger()


def should_clarify(state: DevTeamState) -> Literal["clarification", "continue"]:
    """
    Router: Check if clarification is needed from user.
    """
    logger.debug("router.should_clarify", needs_clarification=state.get("needs_clarification", False))
    if state.get("needs_clarification", False):
        return "clarification"
    return "continue"


def route_after_analyst(state: DevTeamState) -> Literal["clarification", "architect"]:
    """
    Router: After analyst, check if clarification needed.
    """
    logger.debug("router.after_analyst", needs_clarification=state.get("needs_clarification", False))
    if state.get("needs_clarification", False):
        return "clarification"
    return "architect"


def route_after_architect(state: DevTeamState) -> Literal["clarification", "developer"]:
    """
    Router: After architect, check if approval needed.
    """
    logger.debug("router.after_architect", needs_clarification=state.get("needs_clarification", False))
    if state.get("needs_clarification", False):
        return "clarification"
    return "developer"


# Maximum Dev↔QA iterations before escalation
MAX_QA_ITERATIONS_BEFORE_ARCHITECT = 3
MAX_QA_ITERATIONS_BEFORE_HUMAN = 3  # After architect already escalated once


def route_after_qa(
    state: DevTeamState,
) -> Literal["developer", "architect_escalation", "human_escalation", "git_commit", "pm_final"]:
    """
    Router: After QA, determine next step.

    Escalation ladder:
      1) ≤ 3 Dev↔QA iterations → send back to developer
      2) After 3 iterations (architect not yet involved) → architect_escalation
      3) After architect intervened and another 3 iterations → human_escalation
      4) If no issues / approved → git_commit or pm_final
    """
    # If there are issues, apply escalation logic
    if state.get("issues_found"):
        qa_iter = state.get("qa_iteration_count", 0)
        architect_escalated = state.get("architect_escalated", False)

        if not architect_escalated and qa_iter >= MAX_QA_ITERATIONS_BEFORE_ARCHITECT:
            logger.info("router.after_qa", decision="architect_escalation", qa_iter=qa_iter)
            return "architect_escalation"

        if architect_escalated and qa_iter >= MAX_QA_ITERATIONS_BEFORE_HUMAN:
            logger.info("router.after_qa", decision="human_escalation", qa_iter=qa_iter)
            return "human_escalation"

        logger.debug("router.after_qa", decision="developer", issues=len(state.get("issues_found", [])), qa_iter=qa_iter)
        return "developer"

    # If approved, proceed to commit
    test_results = state.get("test_results", {})
    if test_results.get("approved", False):
        logger.debug("router.after_qa", decision="git_commit", approved=True)
        return "git_commit"

    # Otherwise, final PM review
    logger.debug("router.after_qa", decision="pm_final")
    return "pm_final"


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
    Architect reviews repeated Dev↔QA failures and decides
    which issues are truly critical vs cosmetic/waivable.
    """
    from dev_team.agents.architect import get_architect_agent
    agent = get_architect_agent()
    return agent.review_qa_escalation(state, config=config)


def route_after_architect_escalation(
    state: DevTeamState,
) -> Literal["developer", "git_commit"]:
    """
    After architect escalation: if approved → git_commit, else → developer.
    """
    test_results = state.get("test_results", {})
    if test_results.get("approved", False):
        return "git_commit"
    return "developer"


def human_escalation_node(state: DevTeamState) -> dict:
    """
    After both Dev↔QA and Architect escalation failed to converge,
    ask the human for guidance via the HITL interrupt mechanism.

    The node sets needs_clarification=True and pauses the graph.
    """
    issues = state.get("issues_found", [])
    qa_iter = state.get("qa_iteration_count", 0)
    issues_text = "\n".join(f"  - {i}" for i in issues) if issues else "  (see review comments)"

    logger.info("node.human_escalation", qa_iter=qa_iter, issues=len(issues))

    question = (
        f"Dev and QA could not resolve the following issues after "
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
        "clarification_context": "qa_human_escalation",
        "current_agent": "qa",
    }


def git_commit_node(state: DevTeamState) -> dict:
    """
    Commit generated code to GitHub:
      1. Create a feature branch
      2. Commit every code file
      3. Open a pull request

    When no repository or GITHUB_TOKEN is configured the node
    gracefully skips the commit and returns the generated code
    in the summary so it is still visible in the chat.
    """
    code_files = state.get("code_files", [])
    repository = state.get("repository") or os.getenv("GITHUB_DEFAULT_REPO", "")
    task = state.get("task", "AI-generated task")
    logger.info("node.git_commit", repository=repository or "none", files=len(code_files))

    # ------------------------------------------------------------------
    # Guard: no repository → return code in summary
    # ------------------------------------------------------------------
    if not repository:
        logger.warning("node.git_commit.skip", reason="no_repository")
        summary = _build_code_summary(code_files, task)
        return {
            "summary": summary,
            "current_agent": "complete",
        }

    # ------------------------------------------------------------------
    # Guard: no GitHub client (token missing / PyGithub not installed)
    # ------------------------------------------------------------------
    client = get_github_client()
    if client is None:
        logger.error("node.git_commit.skip", reason="github_client_unavailable")
        summary = _build_code_summary(code_files, task)
        return {
            "summary": (
                "⚠️ GitHub integration is not configured (GITHUB_TOKEN missing). "
                "Code was generated but NOT committed.\n\n" + summary
            ),
            "current_agent": "complete",
        }

    # ------------------------------------------------------------------
    # 1. Create a feature branch
    # ------------------------------------------------------------------
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    branch_name = f"ai/task-{ts}"

    try:
        repo = client.get_repo(repository)
        default_branch = repo.default_branch
        base_ref = repo.get_git_ref(f"heads/{default_branch}")
        repo.create_git_ref(
            ref=f"refs/heads/{branch_name}",
            sha=base_ref.object.sha,
        )
        logger.info("git.branch_created", branch=branch_name, base=default_branch)
    except Exception as exc:
        logger.error("git.branch_create_failed", error=str(exc))
        summary = _build_code_summary(code_files, task)
        return {
            "summary": f"⚠️ Failed to create branch on {repository}: {exc}\n\n{summary}",
            "current_agent": "complete",
            "error": str(exc),
        }

    # ------------------------------------------------------------------
    # 2. Commit every code file
    # ------------------------------------------------------------------
    last_sha = None
    committed = 0
    for cf in code_files:
        file_path = cf.get("path", "")
        content = cf.get("content", "")
        if not file_path or not content:
            continue

        commit_msg = f"feat: add {file_path} (AI-generated)"
        try:
            # Check if file exists on the branch
            try:
                existing = repo.get_contents(file_path, ref=branch_name)
                result = repo.update_file(
                    path=file_path,
                    message=commit_msg,
                    content=content,
                    sha=existing.sha,
                    branch=branch_name,
                )
            except Exception:
                result = repo.create_file(
                    path=file_path,
                    message=commit_msg,
                    content=content,
                    branch=branch_name,
                )
            last_sha = result["commit"].sha
            committed += 1
            logger.debug("git.file_committed", path=file_path, sha=last_sha[:8])
        except Exception as exc:
            logger.error("git.file_commit_failed", path=file_path, error=str(exc))

    if committed == 0:
        logger.warning("node.git_commit.skip", reason="no_files_committed")
        summary = _build_code_summary(code_files, task)
        return {
            "summary": f"⚠️ No files were committed to {repository}.\n\n{summary}",
            "current_agent": "complete",
        }

    # ------------------------------------------------------------------
    # 3. Create a pull request
    # ------------------------------------------------------------------
    pr_title = f"[AI-crew] {task[:80]}"
    pr_body = (
        f"## AI-Generated Code\n\n"
        f"**Task:** {task}\n\n"
        f"**Files ({committed}):**\n"
        + "\n".join(f"- `{cf['path']}`" for cf in code_files if cf.get("path"))
        + "\n\n---\n*Created automatically by AI-crew dev team.*"
    )

    try:
        pr = repo.create_pull(
            title=pr_title,
            body=pr_body,
            head=branch_name,
            base=default_branch,
        )
        pr_url = pr.html_url
        logger.info("git.pr_created", url=pr_url)
    except Exception as exc:
        logger.error("git.pr_create_failed", error=str(exc))
        pr_url = None

    return {
        "pr_url": pr_url or f"https://github.com/{repository}/tree/{branch_name}",
        "commit_sha": last_sha or "",
        "summary": (
            f"✅ Created PR with {committed} file(s) on {repository}\n"
            f"Branch: {branch_name}\n"
            f"PR: {pr_url or 'failed to create'}"
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
    5. QA reviews (may send back to developer)
    6. Git commit (if approved)
    7. PM final review
    """
    
    # Create the graph
    logger.info("graph.create")
    builder = StateGraph(DevTeamState)
    
    # Add nodes
    builder.add_node("pm", pm_agent)
    builder.add_node("analyst", analyst_agent)
    builder.add_node("architect", architect_agent)
    builder.add_node("developer", developer_agent)
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

    # Developer -> QA
    builder.add_edge("developer", "qa")

    # QA -> (developer | architect_escalation | human_escalation | git_commit | pm_final)
    builder.add_conditional_edges(
        "qa",
        route_after_qa,
        {
            "developer": "developer",
            "architect_escalation": "architect_escalation",
            "human_escalation": "human_escalation",
            "git_commit": "git_commit",
            "pm_final": "pm_final",
        }
    )

    # Architect escalation → (developer or git_commit)
    builder.add_conditional_edges(
        "architect_escalation",
        route_after_architect_escalation,
        {
            "developer": "developer",
            "git_commit": "git_commit",
        }
    )

    # Human escalation is an interrupt point — after user responds,
    # route to developer to apply the human's guidance.
    builder.add_edge("human_escalation", "developer")

    # Clarification → back to analyst
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
# at execution time (see langgraph_service.py → get_graph()).
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
