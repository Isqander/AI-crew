"""
Development Team Graph

Main LangGraph definition for the AI development team.
"""

from typing import Literal

import os
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.memory import MemorySaver

from .state import DevTeamState
from .agents.pm import pm_agent
from .agents.analyst import analyst_agent
from .agents.architect import architect_agent
from .agents.developer import developer_agent
from .agents.qa import qa_agent


def should_clarify(state: DevTeamState) -> Literal["clarification", "continue"]:
    """
    Router: Check if clarification is needed from user.
    """
    if state.get("needs_clarification", False):
        return "clarification"
    return "continue"


def route_after_analyst(state: DevTeamState) -> Literal["clarification", "architect"]:
    """
    Router: After analyst, check if clarification needed.
    """
    if state.get("needs_clarification", False):
        return "clarification"
    return "architect"


def route_after_architect(state: DevTeamState) -> Literal["clarification", "developer"]:
    """
    Router: After architect, check if approval needed.
    """
    if state.get("needs_clarification", False):
        return "clarification"
    return "developer"


def route_after_qa(state: DevTeamState) -> Literal["developer", "git_commit", "pm_final"]:
    """
    Router: After QA, determine next step.
    """
    # If there are issues, send back to developer
    if state.get("issues_found"):
        return "developer"
    
    # If approved, proceed to commit
    test_results = state.get("test_results", {})
    if test_results.get("approved", False):
        return "git_commit"
    
    # Otherwise, final PM review
    return "pm_final"


def clarification_node(state: DevTeamState) -> dict:
    """
    Human-in-the-loop node for clarification.
    
    This node is an interrupt point - execution pauses here
    until user provides clarification_response.
    """
    return {
        "current_agent": "waiting_for_user",
    }


def process_clarification(state: DevTeamState) -> dict:
    """
    Process clarification response and route to appropriate agent.
    """
    # Clear the clarification flag
    current_agent = state.get("current_agent", "pm")
    
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
    
    if not repository:
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
    print(f"✓ Using PostgreSQL checkpointer: {database_url.split('@')[1] if '@' in database_url else 'configured'}")
    checkpointer = PostgresSaver.from_conn_string(database_url)
else:
    # Development: in-memory storage (states will be lost on restart)
    print("⚠️  WARNING: Using MemorySaver - all states will be lost on restart!")
    print("   Set DATABASE_URL environment variable to use persistent storage.")
    checkpointer = MemorySaver()

graph = create_graph().compile(
    checkpointer=checkpointer,
    interrupt_before=["clarification"],  # Pause for human input
)


# Export for Aegra
__all__ = ["graph", "DevTeamState"]
