"""
Development Team Graph

Main LangGraph definition for the AI development team.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Literal

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.memory import MemorySaver

# NOTE: Aegra loads this file via importlib with module name "graphs.{graph_id}",
# which sets __package__ = "graphs" instead of "graphs.dev_team".
# Relative imports (from .state, from .agents) would resolve against "graphs.*"
# and fail. Use absolute imports based on sys.path (/app/graphs → "dev_team.*").
from dev_team.state import DevTeamState

from dev_team.agents.pm import pm_agent
from dev_team.agents.analyst import analyst_agent
from dev_team.agents.architect import architect_agent
from dev_team.agents.developer import developer_agent
from dev_team.agents.qa import qa_agent
from dev_team.tools.github import get_github_client


def configure_logging() -> None:
    """
    Configure application logging based on environment variables.
    """
    level_name = os.getenv("LOG_LEVEL")
    env_mode = os.getenv("ENV_MODE", "LOCAL").upper()

    if not level_name:
        level_name = "DEBUG" if env_mode == "LOCAL" else "INFO"

    normalized = level_name.upper()
    level = getattr(logging, normalized, logging.INFO)

    root_logger = logging.getLogger()
    if root_logger.handlers:
        root_logger.setLevel(level)
        return

    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


configure_logging()
logger = logging.getLogger(__name__)


def should_clarify(state: DevTeamState) -> Literal["clarification", "continue"]:
    """
    Router: Check if clarification is needed from user.
    """
    logger.debug("Router should_clarify: needs_clarification=%s", state.get("needs_clarification", False))
    if state.get("needs_clarification", False):
        return "clarification"
    return "continue"


def route_after_analyst(state: DevTeamState) -> Literal["clarification", "architect"]:
    """
    Router: After analyst, check if clarification needed.
    """
    logger.debug("Router after_analyst: needs_clarification=%s", state.get("needs_clarification", False))
    if state.get("needs_clarification", False):
        return "clarification"
    return "architect"


def route_after_architect(state: DevTeamState) -> Literal["clarification", "developer"]:
    """
    Router: After architect, check if approval needed.
    """
    logger.debug("Router after_architect: needs_clarification=%s", state.get("needs_clarification", False))
    if state.get("needs_clarification", False):
        return "clarification"
    return "developer"


def route_after_qa(state: DevTeamState) -> Literal["developer", "git_commit", "pm_final"]:
    """
    Router: After QA, determine next step.
    """
    # If there are issues, send back to developer
    if state.get("issues_found"):
        logger.debug("Router after_qa: issues_found=%s -> developer", len(state.get("issues_found", [])))
        return "developer"
    
    # If approved, proceed to commit
    test_results = state.get("test_results", {})
    if test_results.get("approved", False):
        logger.debug("Router after_qa: approved=True -> git_commit")
        return "git_commit"
    
    # Otherwise, final PM review
    logger.debug("Router after_qa: approved=False -> pm_final")
    return "pm_final"


def clarification_node(state: DevTeamState) -> dict:
    """
    Human-in-the-loop node for clarification.
    
    This node is an interrupt point - execution pauses here
    until user provides clarification_response.
    """
    logger.info("Clarification requested. Waiting for user input.")
    return {
        "current_agent": "waiting_for_user",
    }


def process_clarification(state: DevTeamState) -> dict:
    """
    Process clarification response and route to appropriate agent.
    """
    # Clear the clarification flag
    current_agent = state.get("current_agent", "pm")
    logger.info("Processing clarification response for agent=%s", current_agent)
    
    return {
        "needs_clarification": False,
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
    repository = state.get("repository")
    task = state.get("task", "AI-generated task")
    logger.info(
        "Git commit node: repository=%s files=%s",
        repository or "none",
        len(code_files),
    )

    # ------------------------------------------------------------------
    # Guard: no repository → return code in summary
    # ------------------------------------------------------------------
    if not repository:
        logger.warning("No repository specified, skipping git commit.")
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
        logger.error("GitHub client unavailable (GITHUB_TOKEN not set or PyGithub missing).")
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
        logger.info("Created branch %s from %s", branch_name, default_branch)
    except Exception as exc:
        logger.error("Failed to create branch: %s", exc)
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
            logger.debug("Committed %s (%s)", file_path, last_sha[:8])
        except Exception as exc:
            logger.error("Failed to commit %s: %s", file_path, exc)

    if committed == 0:
        logger.warning("No files committed — skipping PR creation.")
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
        logger.info("PR created: %s", pr_url)
    except Exception as exc:
        logger.error("Failed to create PR: %s", exc)
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
    logger.info("Creating development team graph.")
    builder = StateGraph(DevTeamState)
    
    # Add nodes
    builder.add_node("pm", pm_agent)
    builder.add_node("analyst", analyst_agent)
    builder.add_node("architect", architect_agent)
    builder.add_node("developer", developer_agent)
    builder.add_node("qa", qa_agent)
    builder.add_node("clarification", clarification_node)
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
    
    # QA -> (developer or git_commit or pm_final)
    builder.add_conditional_edges(
        "qa",
        route_after_qa,
        {
            "developer": "developer",
            "git_commit": "git_commit",
            "pm_final": "pm_final",
        }
    )
    
    # Clarification -> back to the agent that needed it
    # For simplicity, we route back to analyst
    # In production, this would track which agent requested clarification
    builder.add_edge("clarification", "analyst")
    
    # Git commit -> END
    builder.add_edge("git_commit", END)
    
    # PM final -> END
    builder.add_edge("pm_final", END)
    
    return builder


# ===========================================
# Checkpointer (state persistence)
# ===========================================

def _get_postgres_url() -> str:
    """
    Build a plain ``postgresql://`` connection string for LangGraph's
    PostgresSaver.

    Resolution order:
      1. DATABASE_URL env var (strip +asyncpg / +psycopg2 driver prefix)
      2. Construct from individual POSTGRES_* env vars
      3. Return "" → fallback to MemorySaver
    """
    raw = os.getenv("DATABASE_URL", "")
    if raw:
        # Strip SQLAlchemy async driver prefix:
        #   postgresql+asyncpg://…  →  postgresql://…
        #   postgresql+psycopg2://… →  postgresql://…
        if "+" in raw.split("://")[0]:
            raw = raw.split("+")[0] + raw[raw.index("://"):]
        return raw

    # Construct from POSTGRES_* variables (set by entrypoint.sh)
    host = os.getenv("POSTGRES_HOST", "")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "aicrew")
    user = os.getenv("POSTGRES_USER", "aicrew")
    password = os.getenv("POSTGRES_PASSWORD", "")
    if host and password:
        return f"postgresql://{user}:{password}@{host}:{port}/{db}"

    return ""


# Use PostgreSQL in production, Memory in development
database_url = _get_postgres_url()

if database_url:
    db_host = database_url.split("@")[1].split("/")[0] if "@" in database_url else "configured"
    logger.info("Using PostgreSQL checkpointer: %s", db_host)
    try:
        checkpointer = PostgresSaver.from_conn_string(database_url)
    except Exception as exc:
        logger.error("Failed to create PostgresSaver: %s — falling back to MemorySaver", exc)
        checkpointer = MemorySaver()
else:
    logger.warning("Using MemorySaver — all states will be lost on restart!")
    logger.warning(
        "Set DATABASE_URL or POSTGRES_HOST + POSTGRES_PASSWORD to use persistent storage."
    )
    checkpointer = MemorySaver()

graph = create_graph().compile(
    checkpointer=checkpointer,
    interrupt_before=["clarification"],  # Pause for human input
)
logger.info("Graph compiled with checkpointer=%s", type(checkpointer).__name__)


# Export for Aegra
__all__ = ["graph", "DevTeamState"]
