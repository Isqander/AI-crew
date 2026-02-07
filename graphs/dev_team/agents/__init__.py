"""
Agent definitions for the dev-team graph.

Each agent module exposes:
  - A class (e.g. ``ProjectManagerAgent``)
  - A singleton getter (e.g. ``get_pm_agent()``)
  - A LangGraph node function (e.g. ``pm_agent(state) -> dict``)
"""
from .base import BaseAgent, get_llm, load_prompts
from .pm import pm_agent, ProjectManagerAgent
from .analyst import analyst_agent, AnalystAgent
from .architect import architect_agent, ArchitectAgent
from .developer import developer_agent, DeveloperAgent
from .qa import qa_agent, QAAgent

__all__ = [
    # Base
    "BaseAgent",
    "get_llm",
    "load_prompts",
    # Node functions (used by graph.py)
    "pm_agent",
    "analyst_agent",
    "architect_agent",
    "developer_agent",
    "qa_agent",
    # Classes (for direct instantiation / testing)
    "ProjectManagerAgent",
    "AnalystAgent",
    "ArchitectAgent",
    "DeveloperAgent",
    "QAAgent",
]
