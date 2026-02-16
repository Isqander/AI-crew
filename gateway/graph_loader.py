"""
Graph Loader — shared manifest and config loading.
====================================================

Single source of truth for loading graph manifests and agent
configuration in the gateway.  Used by both ``endpoints/graph.py``
and ``router.py`` to avoid duplicated code and inconsistent paths.
"""

from __future__ import annotations

from pathlib import Path

import structlog
import yaml

logger = structlog.get_logger()

# Base directories (relative to the repo root)
_GRAPHS_DIR = Path(__file__).parent.parent / "graphs"
_CONFIG_DIR = Path(__file__).parent.parent / "config"


def get_graphs_dir() -> Path:
    """Return the absolute path to the ``graphs/`` directory."""
    return _GRAPHS_DIR


def get_config_dir() -> Path:
    """Return the absolute path to the ``config/`` directory."""
    return _CONFIG_DIR


# ────────────────────── Manifest loading ──────────────────────


def load_manifests() -> list[dict]:
    """Scan ``graphs/*/manifest.yaml`` and return parsed manifests.

    Returns:
        List of parsed YAML dicts. Empty list if ``graphs/`` doesn't exist.
    """
    manifests: list[dict] = []
    if not _GRAPHS_DIR.exists():
        return manifests

    for manifest_path in _GRAPHS_DIR.glob("*/manifest.yaml"):
        try:
            data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            if data:
                manifests.append(data)
        except Exception as exc:
            logger.warning("graph_loader.manifest_error",
                           path=str(manifest_path), error=str(exc))
    return manifests


def find_manifest(graph_id: str) -> dict | None:
    """Find a specific graph's manifest by ``name`` field.

    Args:
        graph_id: The graph name to look for.

    Returns:
        Parsed manifest dict, or ``None`` if not found.
    """
    manifests = load_manifests()
    return next((m for m in manifests if m.get("name") == graph_id), None)


# ────────────────────── Agent config ──────────────────────────


def load_agents_yaml() -> dict:
    """Load ``config/agents.yaml`` for agent configuration.

    Returns:
        Parsed YAML dict, or empty dict if file is missing.
    """
    config_path = _CONFIG_DIR / "agents.yaml"
    if not config_path.exists():
        return {}
    try:
        return yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        logger.warning("graph_loader.agents_yaml_error", error=str(exc))
        return {}


# ────────────────────── Prompt loading ────────────────────────


def load_prompt_info(graph_id: str) -> dict:
    """Load prompt summaries for all agents in a graph.

    Returns a dict of ``{agent_name: {"system": str, "templates": [str]}}``.
    System prompt is truncated to 500 chars for UI display.

    Args:
        graph_id: The graph directory name.

    Returns:
        Dict mapping agent names to prompt info.
    """
    prompts_dir = _GRAPHS_DIR / graph_id / "prompts"
    result: dict = {}
    if not prompts_dir.exists():
        return result

    for yaml_file in prompts_dir.glob("*.yaml"):
        agent_name = yaml_file.stem
        try:
            data = yaml.safe_load(yaml_file.read_text(encoding="utf-8")) or {}
            system = data.get("system", "")
            templates = [k for k in data.keys() if k != "system"]
            result[agent_name] = {
                "system": system[:500],
                "templates": templates,
            }
        except Exception as exc:
            logger.warning("graph_loader.prompt_error",
                           agent=agent_name, error=str(exc))
    return result
