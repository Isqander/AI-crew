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

Constants:
  - ``PROJECT_ROOT`` — absolute path to the project root directory
"""

from pathlib import Path as _Path


def _find_project_root() -> _Path:
    """Find the project root directory (the one containing config/ and graphs/).

    Searches upward from this file's location for a directory that contains
    both ``config/`` and ``graphs/`` subdirectories. This is more robust than
    counting ``..`` levels, which breaks if the package is relocated.
    """
    current = _Path(__file__).resolve().parent
    for _ in range(10):
        if (current / "config").is_dir() and (current / "graphs").is_dir():
            return current
        current = current.parent
    # Fallback: common/ is at graphs/common/, so parent.parent is project root
    return _Path(__file__).resolve().parent.parent.parent


PROJECT_ROOT = _find_project_root()


from .types import CodeFile, UserStory, ArchitectureDecision
from .utils import build_code_summary, format_code_files
from .git import make_git_commit_node
from .logging import configure_logging

__all__ = [
    # Project root
    "PROJECT_ROOT",
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
