"""
Graph Endpoints
===============

- ``GET /graph/list``              — list available graphs from manifest files
- ``GET /graph/topology/{id}``     — graph topology for visualisation
- ``GET /graph/config/{id}``       — agent LLM configuration
"""

from __future__ import annotations

from pathlib import Path

import structlog
import yaml
from fastapi import APIRouter, Depends, HTTPException

from gateway.auth import get_current_user
from gateway.models import (
    AgentBrief,
    AgentConfig,
    GraphConfigResponse,
    GraphListItem,
    GraphListResponse,
    GraphTopologyResponse,
    PromptInfo,
    User,
)

logger = structlog.get_logger()
router = APIRouter(prefix="/graph", tags=["graph"])

# Paths relative to the repo root
_GRAPHS_DIR = Path(__file__).parent.parent.parent / "graphs"
_CONFIG_DIR = Path(__file__).parent.parent.parent / "config"


def _load_manifests() -> list[dict]:
    """Scan ``graphs/*/manifest.yaml`` and return parsed manifests."""
    manifests: list[dict] = []
    if not _GRAPHS_DIR.exists():
        return manifests
    for manifest_path in _GRAPHS_DIR.glob("*/manifest.yaml"):
        try:
            data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            if data:
                manifests.append(data)
        except Exception as exc:
            logger.warning("graph.manifest_error", path=str(manifest_path), error=str(exc))
    return manifests


def _load_agents_yaml() -> dict:
    """Load ``config/agents.yaml`` for agent configuration."""
    config_path = _CONFIG_DIR / "agents.yaml"
    if not config_path.exists():
        return {}
    try:
        return yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        logger.warning("graph.agents_yaml_error", error=str(exc))
        return {}


def _load_prompt_info(graph_id: str) -> dict[str, PromptInfo]:
    """Load prompt summaries for all agents in a graph."""
    prompts_dir = _GRAPHS_DIR / graph_id / "prompts"
    result: dict[str, PromptInfo] = {}
    if not prompts_dir.exists():
        return result

    for yaml_file in prompts_dir.glob("*.yaml"):
        agent_name = yaml_file.stem
        try:
            data = yaml.safe_load(yaml_file.read_text(encoding="utf-8")) or {}
            system = data.get("system", "")
            templates = [k for k in data.keys() if k != "system"]
            result[agent_name] = PromptInfo(
                system=system[:500],  # Truncate for UI
                templates=templates,
            )
        except Exception as exc:
            logger.warning("graph.prompt_error", agent=agent_name, error=str(exc))
    return result


# ────────────────────── Endpoints ──────────────────────


@router.get("/list", response_model=GraphListResponse)
async def list_graphs(_user: User = Depends(get_current_user)) -> GraphListResponse:
    """List all available graphs from their manifest.yaml files."""
    manifests = _load_manifests()
    items = []
    for m in manifests:
        agents = [AgentBrief(id=a["id"], display_name=a["display_name"]) for a in m.get("agents", [])]
        items.append(
            GraphListItem(
                graph_id=m.get("name", "unknown"),
                display_name=m.get("display_name", ""),
                description=m.get("description", ""),
                version=m.get("version", "0.0.0"),
                task_types=m.get("task_types", []),
                agents=agents,
                features=m.get("features", []),
            )
        )
    logger.info("graph.list", count=len(items),
                graph_ids=[i.graph_id for i in items])
    return GraphListResponse(graphs=items)


@router.get("/topology/{graph_id}", response_model=GraphTopologyResponse)
async def graph_topology(graph_id: str, _user: User = Depends(get_current_user)) -> GraphTopologyResponse:
    """Return topology, agent configs, and prompt info for visualisation."""
    logger.info("graph.topology_request", graph_id=graph_id)
    # Find manifest
    manifests = _load_manifests()
    manifest = next((m for m in manifests if m.get("name") == graph_id), None)
    if not manifest:
        logger.warning("graph.topology_not_found", graph_id=graph_id,
                       available=[m.get("name") for m in manifests])
        raise HTTPException(status_code=404, detail=f"Graph '{graph_id}' not found")

    # Agent configs from agents.yaml
    agents_yaml = _load_agents_yaml()
    agent_configs: dict[str, AgentConfig] = {}
    for agent_def in manifest.get("agents", []):
        aid = agent_def["id"]
        role = agent_def.get("role", aid)
        cfg = agents_yaml.get("agents", {}).get(role, {})
        defaults = agents_yaml.get("defaults", {})
        agent_configs[aid] = AgentConfig(
            model=cfg.get("model", "unknown"),
            temperature=cfg.get("temperature", defaults.get("temperature", 0.7)),
            fallback_model=cfg.get("fallback_model"),
            endpoint=cfg.get("endpoint", defaults.get("endpoint", "default")),
        )

    # Prompts
    prompts = _load_prompt_info(graph_id)

    # Topology — try to get from compiled graph
    topology = _get_graph_topology(graph_id)

    return GraphTopologyResponse(
        graph_id=graph_id,
        topology=topology,
        agents=agent_configs,
        prompts=prompts,
        manifest=manifest,
    )


@router.get("/config/{graph_id}", response_model=GraphConfigResponse)
async def graph_config(graph_id: str, _user: User = Depends(get_current_user)) -> GraphConfigResponse:
    """Return agent LLM configuration for a graph."""
    manifests = _load_manifests()
    manifest = next((m for m in manifests if m.get("name") == graph_id), None)
    if not manifest:
        raise HTTPException(status_code=404, detail=f"Graph '{graph_id}' not found")

    agents_yaml = _load_agents_yaml()
    agent_configs: dict[str, AgentConfig] = {}
    for agent_def in manifest.get("agents", []):
        aid = agent_def["id"]
        role = agent_def.get("role", aid)
        cfg = agents_yaml.get("agents", {}).get(role, {})
        defaults = agents_yaml.get("defaults", {})
        agent_configs[aid] = AgentConfig(
            model=cfg.get("model", "unknown"),
            temperature=cfg.get("temperature", defaults.get("temperature", 0.7)),
            fallback_model=cfg.get("fallback_model"),
            endpoint=cfg.get("endpoint", defaults.get("endpoint", "default")),
        )

    return GraphConfigResponse(graph_id=graph_id, agents=agent_configs)


def _get_graph_topology(graph_id: str) -> dict:
    """Try to extract the graph topology as a JSON-serialisable dict.

    Falls back to an empty ``{nodes: [], edges: []}`` if the graph
    cannot be loaded (common in test environments without full deps).
    """
    try:
        # Import the compiled graph for its topology
        import importlib

        mod = importlib.import_module(f"graphs.{graph_id}.graph")
        graph = getattr(mod, "graph", None)
        if graph and hasattr(graph, "get_graph"):
            raw = graph.get_graph().to_json()
            return raw if isinstance(raw, dict) else {"raw": str(raw)}
    except Exception as exc:
        logger.debug("graph.topology_fallback", graph_id=graph_id, error=str(exc))

    return {"nodes": [], "edges": []}
