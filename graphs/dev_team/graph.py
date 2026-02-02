"""
Development Team Graph

Main LangGraph definition for the AI development team.
"""

import logging
import os
from typing import Literal

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.memory import MemorySaver

from .state import DevTeamState

from .agents.pm import pm_agent
from .agents.analyst import analyst_agent
from .agents.architect import architect_agent
from .agents.developer import developer_agent
from .agents.qa import qa_agent


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
    Node for committing code to GitHub.
    
    In production, this would use the GitHub tools to:
    1. Create a branch
    2. Commit all code files
    3. Create a pull request
    """
    code_files = state.get("code_files", [])
    repository = state.get("repository")
    logger.info("Git commit node: repository=%s files=%s", repository or "none", len(code_files))
    
    if not repository:
        logger.warning("No repository specified, skipping git commit.")
        return {
            "summary": f"Code generation complete. {len(code_files)} file(s) generated. No repository specified for commit.",
            "current_agent": "complete",
        }
    
    # In a real implementation, we would:
    # 1. Create a branch
    # 2. Commit each file
    # 3. Create a PR
    
    # For now, simulate success
    return {
        "pr_url": f"https://github.com/{repository}/pull/1",
        "commit_sha": "abc123",
        "summary": f"Created PR with {len(code_files)} file(s)",
        "current_agent": "complete",
    }


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


# Create the compiled graph
# Use PostgreSQL in production, Memory in development
database_url = os.getenv("DATABASE_URL")

if database_url:
    # Production: persistent storage with PostgreSQL
    db_host = database_url.split('@')[1] if '@' in database_url else 'configured'
    logger.info(f"Using PostgreSQL checkpointer: {db_host}")
    checkpointer = PostgresSaver.from_conn_string(database_url)
else:
    # Development: in-memory storage (states will be lost on restart)
    logger.warning("Using MemorySaver - all states will be lost on restart!")
    logger.warning("Set DATABASE_URL environment variable to use persistent storage.")
    checkpointer = MemorySaver()

graph = create_graph().compile(
    checkpointer=checkpointer,
    interrupt_before=["clarification"],  # Pause for human input
)
logger.info("Graph compiled with checkpointer=%s", type(checkpointer).__name__)


# Export for Aegra
__all__ = ["graph", "DevTeamState"]
