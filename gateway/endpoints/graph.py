"""
Graph Endpoints
===============

- ``GET /graph/list``              — list available graphs from manifest files
- ``GET /graph/topology/{id}``     — graph topology for visualisation
- ``GET /graph/config/{id}``       — agent LLM configuration
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException

from gateway.auth import get_current_user
from gateway.graph_loader import (
    load_manifests,
    load_agents_yaml,
    load_prompt_info,
    get_graphs_dir,
)
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


# ────────────────────── Endpoints ──────────────────────


@router.get("/list", response_model=GraphListResponse)
async def list_graphs(_user: User = Depends(get_current_user)) -> GraphListResponse:
    """List all available graphs from their manifest.yaml files."""
    manifests = load_manifests()
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
    manifests = load_manifests()
    manifest = next((m for m in manifests if m.get("name") == graph_id), None)
    if not manifest:
        logger.warning("graph.topology_not_found", graph_id=graph_id,
                       available=[m.get("name") for m in manifests])
        raise HTTPException(status_code=404, detail=f"Graph '{graph_id}' not found")

    # Agent configs from agents.yaml
    agents_yaml = load_agents_yaml()
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
    # Load prompt info and convert to PromptInfo models
    raw_prompts = load_prompt_info(graph_id)
    prompts = {
        name: PromptInfo(system=info["system"], templates=info["templates"])
        for name, info in raw_prompts.items()
    }

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
    manifests = load_manifests()
    manifest = next((m for m in manifests if m.get("name") == graph_id), None)
    if not manifest:
        raise HTTPException(status_code=404, detail=f"Graph '{graph_id}' not found")

    agents_yaml = load_agents_yaml()
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

    Falls back to a manifest-based topology if the compiled graph
    cannot be loaded (common in test environments without full deps).
    """
    try:
        # Import the compiled graph for its topology
        import importlib

        mod = importlib.import_module(f"graphs.{graph_id}.graph")
        graph = getattr(mod, "graph", None)
        if graph and hasattr(graph, "get_graph"):
            raw = graph.get_graph().to_json()
            logger.info("graph.topology_loaded", graph_id=graph_id,
                        nodes=len(raw.get("nodes", [])) if isinstance(raw, dict) else "?")
            return raw if isinstance(raw, dict) else {"raw": str(raw)}
        logger.warning("graph.topology_no_graph_attr", graph_id=graph_id,
                       has_graph=graph is not None,
                       has_get_graph=hasattr(graph, "get_graph") if graph else False)
    except Exception as exc:
        logger.warning("graph.topology_import_failed", graph_id=graph_id,
                       error=str(exc), error_type=type(exc).__name__)

    # Fallback: build topology from manifest
    return _build_topology_from_manifest(graph_id)


def _build_topology_from_manifest(graph_id: str) -> dict:
    """Build a simplified topology from manifest.yaml when graph import fails."""
    import yaml
    manifest_path = get_graphs_dir() / graph_id / "manifest.yaml"
    if not manifest_path.exists():
        return {"nodes": [], "edges": []}

    try:
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {"nodes": [], "edges": []}

    agents = manifest.get("agents", [])
    if not agents:
        return {"nodes": [], "edges": []}

    nodes = [{"id": a["id"], "type": "runnable", "data": {}} for a in agents]
    edges = []
    for i in range(len(agents) - 1):
        edges.append({"source": agents[i]["id"], "target": agents[i + 1]["id"]})

    logger.info("graph.topology_from_manifest", graph_id=graph_id, nodes=len(nodes))
    return {"nodes": nodes, "edges": edges}
