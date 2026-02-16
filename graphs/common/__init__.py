"""
Shared code for all AI-crew graphs.
====================================

This module contains types, utilities, and reusable node functions
that are used across multiple graph definitions.

Centralising them here eliminates duplication and ensures consistency
when adding new graphs.

Modules:
  - ``types``   — shared TypedDicts (CodeFile, UserStory, etc.)
  - ``utils``   — formatting helpers (build_code_summary, format_code_files)
  - ``git``     — reusable git_commit_node logic
  - ``logging`` — structlog configuration (configure_logging)
"""

from .types import CodeFile, UserStory, ArchitectureDecision
from .utils import build_code_summary, format_code_files
from .git import make_git_commit_node
from .logging import configure_logging

__all__ = [
    # Types
    "CodeFile",
    "UserStory",
    "ArchitectureDecision",
    # Utils
    "build_code_summary",
    "format_code_files",
    # Git
    "make_git_commit_node",
    # Logging
    "configure_logging",
]
