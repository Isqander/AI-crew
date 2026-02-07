"""
Development Team Graph Package
===============================

Multi-agent workflow: PM -> Analyst -> Architect -> Developer -> QA -> Git.

NOTE: Do NOT import ``graph`` here to avoid circular imports.
Aegra loads ``graph.py`` directly via importlib (see ``aegra.json``).
"""
from .state import DevTeamState

__all__ = ["DevTeamState"]
