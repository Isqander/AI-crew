"""
Agent definitions for the dev-team graph.

Each agent module exposes:
  - A class (e.g. ``ProjectManagerAgent``)
  - A singleton getter (e.g. ``get_pm_agent()``)
  - A LangGraph node function (e.g. ``pm_agent(state) -> dict``)
"""
from .base import BaseAgent, get_llm, get_llm_with_fallback, load_prompts
from .pm import pm_agent, ProjectManagerAgent
from .analyst import analyst_agent, AnalystAgent
from .architect import architect_agent, ArchitectAgent
from .developer import developer_agent, DeveloperAgent
from .reviewer import reviewer_agent, ReviewerAgent
from .qa import qa_agent, QAAgent
from .security import security_agent, SecurityAgent
from .devops import devops_agent, DevOpsAgent

__all__ = [
    # Base
    "BaseAgent",
    "get_llm",
    "get_llm_with_fallback",
    "load_prompts",
    # Node functions (used by graph.py)
    "pm_agent",
    "analyst_agent",
    "architect_agent",
    "developer_agent",
    "reviewer_agent",
    "qa_agent",
    "security_agent",
    "devops_agent",
    # Classes (for direct instantiation / testing)
    "ProjectManagerAgent",
    "AnalystAgent",
    "ArchitectAgent",
    "DeveloperAgent",
    "ReviewerAgent",
    "QAAgent",
    "SecurityAgent",
    "DevOpsAgent",
]
